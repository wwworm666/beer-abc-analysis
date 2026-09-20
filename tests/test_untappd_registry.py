"""Regression cases for false name matches and immutable identity decisions."""
from copy import deepcopy
import unittest

from core.untappd_registry import load_registry, resolve_beer
from scripts.build_untappd_registry import alias_key, beer_id


class UntappdRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()
        cls.by_article = {r["iiko_article"]: r for r in cls.registry["products"].values()
                          if r["used_last_two_years"]}

    def lookup(self, article, registry=None):
        return resolve_beer(registry or self.registry, self.by_article[article]["iiko_product_id"])

    def test_owner_identity_wins_over_previous_hints(self):
        for article, bid in [("03312", "64178"), ("3030501423", "4932231"), ("03951", "6758"),
                             ("63244", "2261200"), ("62796", "3425133"), ("63931", "4585406"),
                             ("63324", "5338809"), ("3030502003", "5070663"), ("64531", "2576678"),
                             ("62687", "5368981"), ("63812", "1656905"), ("3030502191", "4725176"),
                             ("62156", "41289"), ("3030501303", "4276330"), ("3030501292", "4276330"),
                             ("64381", "4435453"), ("3030501558", "561371"), ("3030501198", "2976679"),
                             ("00212", "358"), ("3030501315", "6112093"), ("63158", "1187303"),
                             ("3030501813", "3703753"), ("3030501830", "4158838"), ("3030502459", "4806516"),
                             ("3030502428", "3974035"), ("3030502409", "3636325"), ("3030501089", "6029292")]:
            self.assertEqual(self.lookup(article)["id"], bid)
            self.assertEqual(self.by_article[article]["decision"]["confirmation_origin"], "owner")

    def test_owner_corrections_keep_lagers_and_strong_beer_distinct(self):
        self.assertNotEqual(self.lookup("63244")["id"], self.lookup("62687")["id"])
        self.assertEqual(self.lookup("62687")["id"], self.lookup("63914")["id"])
        self.assertEqual(self.lookup("62156")["style"], "Belgian Quadrupel")
        for article, rejected in [("63244", "4817193"), ("62687", "55784"), ("62156", "9601")]:
            decision = self.by_article[article]["decision"]
            self.assertIn(rejected, decision["rejected_candidate_ids"])
            self.assertTrue(decision["owner_confirmation"]["answer"])
            self.assertTrue(decision["previous_decisions"])

    def test_sweetness_is_not_collapsed(self):
        self.assertEqual(self.lookup("03051")["id"], "4061651")
        self.assertEqual(self.lookup("01989")["id"], "4061644")
        self.assertNotEqual(alias_key("КЕГ Rustiq полусладкий 30 л"), alias_key("КЕГ Rustiq полусухой 30 л"))

    def test_name_and_article_never_resolve(self):
        row = self.by_article["03312"]
        for key in (row["iiko_name"], row["iiko_article"], "00000000-0000-0000-0000-000000000000", None):
            self.assertIsNone(resolve_beer(self.registry, key))

    def test_rename_keeps_explicit_guid_decision(self):
        registry = deepcopy(self.registry)
        guid = self.by_article["03312"]["iiko_product_id"]
        registry["products"][guid]["iiko_name"] = "Другое локальное название"
        self.assertEqual(resolve_beer(registry, guid)["id"], "64178")

    def test_unresolved_recipe_does_not_get_candidate(self):
        for status in ("needs_variant", "needs_identity", "needs_source", "skipped", "excluded", "approximate"):
            registry = deepcopy(self.registry)
            row = registry["products"][self.by_article["3030501705"]["iiko_product_id"]]
            self.assertTrue(row["candidates"])
            row["status"] = row["decision"]["status"] = status
            self.assertIsNone(self.lookup("3030501705", registry))

    def test_two_local_cards_can_share_one_external_identity(self):
        self.assertEqual(self.lookup("3030502489")["id"], self.lookup("63424")["id"])
        self.assertEqual(self.lookup("3030501292")["id"], self.lookup("3030501303")["id"])
        self.assertEqual(self.lookup("3030501292")["id"], "4276330")

    def test_corrupt_evidence_or_id_fails_closed(self):
        for mutation in ("evidence", "bid", "host", "state"):
            registry = deepcopy(self.registry)
            row = registry["products"][self.by_article["03312"]["iiko_product_id"]]
            if mutation == "evidence":
                row["decision"]["evidence_urls"] = []
            elif mutation == "bid":
                row["decision"]["untappd_beer_id"] = "1"
            elif mutation == "host":
                registry["beers"]["64178"]["url"] = "https://untappd.com.example.org/b/zubr/64178"
            else:
                row["decision"]["status"] = "needs_variant"
            self.assertIsNone(self.lookup("03312", registry))

    def test_returned_card_cannot_mutate_loaded_registry(self):
        card = self.lookup("03312")
        card["beer_name"] = "changed"
        self.assertEqual(self.lookup("03312")["beer_name"], "Zubr Gold")

    def test_unknown_ibu_stays_unknown(self):
        self.assertIsNone(self.lookup("03312")["ibu"])

    def test_url_requires_concrete_primary_card(self):
        self.assertEqual(beer_id("https://untappd.com/b/arbitrary-slug/64178"), "64178")
        for url in ("http://untappd.com/b/zubr/64178", "https://untappd.com.evil/b/zubr/64178",
                    "https://user@untappd.com/b/zubr/64178", "https://untappd.com/search?q=zubr"):
            with self.assertRaises(ValueError):
                beer_id(url)

    def test_all_verified_rows_are_resolvable(self):
        for guid, row in self.registry["products"].items():
            self.assertEqual(resolve_beer(self.registry, guid) is not None, row["status"] == "verified", guid)

    def test_reused_article_cannot_replace_another_product(self):
        rows = [r for r in self.registry["products"].values() if r["iiko_article"] == "64157"]
        self.assertEqual(len(rows), 2)
        beers = {resolve_beer(self.registry, r["iiko_product_id"])["id"] for r in rows}
        self.assertEqual(len(beers), 2)
        self.assertIn("1589", beers)
        self.assertIsNone(resolve_beer(self.registry, "64157"))
        kona = self.registry["products"]["ea93f445-6e63-4b49-a9f0-b32c7b214157"]
        cider = self.registry["products"]["113bd2a1-7e0d-459b-949e-cbfa90e71173"]
        self.assertEqual(kona["iiko_article"], cider["iiko_article"])
        self.assertEqual(resolve_beer(self.registry, kona["iiko_product_id"])["id"], "9657")
        self.assertIsNone(resolve_beer(self.registry, cider["iiko_product_id"]))

    def test_full_catalog_review_keeps_unidentifiable_card_unlinked(self):
        rows = self.registry["products"]
        self.assertEqual(len(rows), 479)
        self.assertTrue(all(r["decision"] for r in rows.values()))
        unnamed = rows["5f23dad2-5ff5-4e57-ac31-1fa23b244c40"]
        self.assertEqual(unnamed["iiko_name"], "1")
        self.assertEqual(unnamed["status"], "excluded")
        self.assertIsNone(resolve_beer(self.registry, unnamed["iiko_product_id"]))

    def test_recovered_sources_do_not_reuse_wrong_legacy_beer(self):
        self.assertEqual(self.lookup("00608")["id"], "431371")
        self.assertEqual(self.lookup("62197")["id"], "3991487")
        self.assertEqual(self.lookup("3030501398")["id"], "4588361")


if __name__ == "__main__":
    unittest.main()
