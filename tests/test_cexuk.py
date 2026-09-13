"""No network. Every fixture is the shape of a real hit from the UK index,
read on 2026-09-13."""
import io
import json
import unittest
from unittest import mock

import cexuk
from cexuk import client
from cexuk.__main__ import main


def hit(**kw):
    h = {"boxId": "4548736112117B",
         "boxName": "Sony WH-1000XM4 Wireless Noise-Canceling Headphones Over-Ear - Black, B",
         "sellPrice": 145, "cashPriceCalculated": 82, "exchangePriceCalculated": 100,
         "firstPrice": 300, "buyPerc": 57, "exchangePerc": 69, "origin": "UK",
         "categoryName": "Headphones", "superCatName": "Electronics",
         "stores": ["Bromley", "Leeds", "Solihull"], "ecomQuantity": 30,
         "previousPrice": 140, "priceLastChanged": "2026-07-29 02:00:02",
         "discontinued": 0, "boxBuyAllowed": 1}
    h.update(kw)
    return h


def serve(hits):
    """Patch urlopen to answer with these hits; return the patch for inspection."""
    def fake(req, timeout=None):
        cm = mock.MagicMock()
        cm.__enter__.return_value = io.BytesIO(json.dumps({"results": [{"hits": hits}]}).encode())
        return cm
    return mock.patch.object(client.urllib.request, "urlopen", side_effect=fake)


class Base(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(client, "MIN_INTERVAL", 0)
        p.start()
        self.addCleanup(p.stop)


class Parsing(Base):
    def test_fields(self):
        r = cexuk.row_from_hit(hit())
        self.assertEqual((r.name[:15], r.grade), ("Sony WH-1000XM4", "B"))
        self.assertEqual((r.sell_gbp, r.cash_gbp, r.voucher_gbp), (145.0, 82.0, 100.0))
        self.assertEqual((r.cash_pct, r.voucher_pct, r.launch_gbp), (57, 69, 300.0))
        self.assertEqual((r.category, r.super_category), ("Headphones", "Electronics"))
        self.assertEqual((r.stores, r.online_qty), (("Bromley", "Leeds", "Solihull"), 30))
        self.assertEqual((r.previous_gbp, r.price_changed), (140.0, "2026-07-29"))

    def test_grade_without_a_comma(self):
        r = cexuk.row_from_hit(hit(boxName="Apple iPhone 13 128GB Midnight, Unlocked B"))
        self.assertEqual((r.grade, r.name), ("B", "Apple iPhone 13 128GB Midnight, Unlocked"))

    def test_grades_are_one_product(self):
        a = cexuk.row_from_hit(hit(boxId="4548736112117A", boxName="x, A"))
        b = cexuk.row_from_hit(hit())
        self.assertEqual(a.product_id, b.product_id)

    def test_missing_fields_default(self):
        h = hit()
        for k in ("priceLastChanged", "previousPrice", "stores", "categoryName", "ecomQuantity"):
            h.pop(k)
        r = cexuk.row_from_hit(h)
        self.assertEqual((r.price_changed, r.stores, r.online_qty), ("", (), 0))
        self.assertEqual(cexuk.price_move(r), "")


class Requests(Base):
    def test_uk_only(self):
        with serve([hit(), hit(boxId="X1B", origin="IE")]):
            self.assertEqual([r.box_id for r in cexuk.search("Sony WH-1000XM4")], ["4548736112117B"])

    def test_honest_user_agent(self):
        with serve([hit()]) as u:
            cexuk.search("Sony WH-1000XM4")
        ua = u.call_args[0][0].get_header("User-agent")
        self.assertTrue(ua.startswith("cex-uk-prices/"))
        self.assertNotIn("Mozilla", ua)

    def test_a_dead_lookup_is_absent_not_zero(self):
        with mock.patch.object(client.urllib.request, "urlopen",
                               side_effect=client.urllib.error.URLError("down")):
            r = cexuk.lookup("Sony WH-1000XM4")
        self.assertEqual(r["rows"], [])
        self.assertNotIn("cash", r)

    def test_requests_are_paced(self):
        client.MIN_INTERVAL = 0.2   # the setUp patch restores it
        with serve([hit()]), mock.patch.object(client.time, "sleep") as sleep:
            cexuk.search("a"); cexuk.search("b")
        self.assertTrue(sleep.called)


class TheMatchGate(Base):
    def test_measured_wrong_products_are_rejected(self):
        """CeX's fuzzy search, as measured on 2026-09-12."""
        self.assertLess(cexuk.match_score("Raspberry Pi Argon ONE with SSD",
                                          "Raspberry Pi 500+/Cortex-A76/16GB Ram/256GB SSD/Raspbian/UK"), cexuk.MIN_MATCH)
        self.assertLess(cexuk.match_score("Argon ONE M.2 case",
                                          "Hercule Poirot - The First Cases"), cexuk.MIN_MATCH)
        self.assertEqual(cexuk.match_score("Casio FX-CG50 Graphing Calculator",
                                           "Casio FX-CG20 Graphing Calculator"), 0.0)

    def test_measured_right_products_pass(self):
        self.assertGreaterEqual(cexuk.match_score("Sony WH-1000XM4",
            "Sony WH-1000XM4 Wireless Noise-Canceling Headphones Over-Ear - Black"), cexuk.MIN_MATCH)
        self.assertGreaterEqual(cexuk.match_score("Xiaomi Mi TV Box S 3rd Gen",
            "Xiaomi Mi TV Box S 4K 3rd Gen"), cexuk.MIN_MATCH)

    def test_lookup_keeps_only_the_product(self):
        pi = hit(boxId="PI500B", boxName="Raspberry Pi 500+/Cortex-A76/16GB Ram/256GB SSD/Raspbian/UK, B", cashPriceCalculated=136)
        with serve([pi]):
            r = cexuk.lookup("Raspberry Pi Argon ONE with SSD")
        self.assertEqual(r["rows"], [])
        self.assertNotIn("cash", r)          # never "CeX pays £136" for a different product
        self.assertEqual(len(r["rejected"]), 1)


class Lookup(Base):
    def test_numbers_come_from_one_grade_of_one_product(self):
        a = hit(boxId="4548736112117A", boxName="Sony WH-1000XM4 - Black, A", sellPrice=170,
                cashPriceCalculated=96, exchangePriceCalculated=117,
                stores=["Leeds", "Bristol"], ecomQuantity=5)
        other = hit(boxId="4548736112116B", boxName="Sony WH-1000XM4 - Silver, B",
                    cashPriceCalculated=40, stores=["Harrow"], ecomQuantity=9)
        with serve([hit(), a, other]):
            r = cexuk.lookup("Sony WH-1000XM4")
        self.assertEqual((r["sell"], r["cash"], r["voucher"], r["grade"]), (170.0, 96.0, 117.0, "A"))
        self.assertEqual(r["stores"], ["Bristol", "Bromley", "Leeds", "Solihull"])
        self.assertEqual(r["online_qty"], 35)
        self.assertEqual(r["products"], 2)

    def test_a_refusal_is_not_a_zero_offer(self):
        nest = hit(boxId="NEST2B", boxName="Google Nest Mini (2nd Gen)- Charcoal, B", sellPrice=35,
                   previousPrice=35, cashPriceCalculated=0, exchangePriceCalculated=0,
                   discontinued=1, boxBuyAllowed=1)
        with serve([nest]):
            r = cexuk.lookup("Google Nest Mini 2nd Gen")
        self.assertEqual(r["cash"], 0.0)
        self.assertTrue(r["discontinued"])
        self.assertIn("will not buy", r["note"])
        self.assertIn("discontinued", r["note"])

    def test_price_move(self):
        self.assertEqual(cexuk.price_move(cexuk.row_from_hit(hit())), "CeX raised it £140 → £145 on 29 Jul 2026")
        self.assertTrue(cexuk.price_move(cexuk.row_from_hit(hit(sellPrice=120))).startswith("CeX cut it"))

    def test_floor_warning(self):
        self.assertIn("below the £82", cexuk.floor_warning(60, 82))
        self.assertEqual(cexuk.floor_warning(90, 82), "")
        self.assertEqual(cexuk.floor_warning(60, 0), "")


class Cli(Base):
    def test_exit_codes_tell_no_match_from_a_match(self):
        with serve([hit()]), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(main(["Sony WH-1000XM4", "--ask", "60"]), 0)
        self.assertIn("£60.00 is below the £82", out.getvalue())
        with serve([]), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["Sony WH-1000XM4"]), 1)

    def test_json(self):
        with serve([hit()]), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            main(["Sony WH-1000XM4", "--json"])
        doc = json.loads(out.getvalue())
        self.assertEqual(doc["cash"], 82.0)
        self.assertEqual(doc["rows"][0]["grade"], "B")


if __name__ == "__main__":
    unittest.main()
