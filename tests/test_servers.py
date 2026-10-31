import unittest
from bulkrr_servers import validate_profiles, legacy_profiles, public_profiles


class ServerProfileTests(unittest.TestCase):
    def test_migrates_old_settings(self):
        result = legacy_profiles({"radarr_url": "http://localhost:7878", "sonarr_url": "https://media.example/"})
        self.assertEqual([p["id"] for p in result], ["radarr_default", "sonarr_default"])
        self.assertEqual(result[1]["url"], "https://media.example")

    def test_multiple_instances(self):
        profiles = validate_profiles([
            {"id": "sonarr_a", "kind": "sonarr", "url": "http://host-a:8989"},
            {"id": "sonarr_b", "kind": "sonarr", "url": "http://host-b:8989"},
        ])
        self.assertEqual(len(profiles), 2)

    def test_rejects_duplicate_and_credentials(self):
        one = {"id": "primary", "kind": "radarr", "url": "http://host:7878"}
        with self.assertRaises(ValueError):
            validate_profiles([one, one])
        with self.assertRaises(ValueError):
            validate_profiles([{**one, "url": "http://user:pass@host"}])

    def test_rejects_missing_host_and_query(self):
        base = {"id": "one", "kind": "sonarr", "url": "http://host:8989"}
        for url in ("http://", "https://host?apikey=secret", "http://host#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_profiles([{**base, "url": url}])

    def test_saved_profiles_have_no_key(self):
        profiles = public_profiles([{"id": "one", "kind": "radarr", "url": "http://host", "key": "secret"}])
        self.assertNotIn("key", profiles[0])

    def test_explicit_multi_instance_routing(self):
        from bulkrr_servers import route_to_profiles
        profiles = [
            {"id": "sonarr_a", "kind": "sonarr", "url": "http://host-a:8989"},
            {"id": "sonarr_b", "kind": "sonarr", "url": "http://host-b:8989"},
            {"id": "radarr_a", "kind": "radarr", "url": "http://host-c:7878"},
        ]
        assignments = [
            {"item_id": 1, "kind": "sonarr", "profile_id": "sonarr_b"},
            {"item_id": 2, "kind": "radarr", "profile_id": "radarr_a"},
            {"item_id": 3, "kind": "sonarr", "profile_id": "sonarr_a"},
            {"item_id": 4, "kind": "sonarr", "profile_id": "sonarr_b"},
        ]
        result = route_to_profiles(profiles, assignments)
        self.assertEqual([(r["profile"]["id"], r["item_ids"]) for r in result],
                         [("sonarr_b", [1, 4]), ("radarr_a", [2]), ("sonarr_a", [3])])
        self.assertNotIn("key", result[0]["profile"])

    def test_multi_instance_routing_rejects_unsafe_or_ambiguous_targets(self):
        from bulkrr_servers import route_to_profiles
        profiles = [{"id": "sonarr_a", "kind": "sonarr", "url": "http://host:8989"}]
        valid = {"item_id": 1, "kind": "sonarr", "profile_id": "sonarr_a"}
        invalid = [
            [{**valid, "profile_id": "missing"}],
            [{**valid, "kind": "radarr"}],
            [{**valid, "item_id": True}],
            [valid, valid],
            [{**valid, "profile_id": None}],
            [valid] * 501,
        ]
        for assignments in invalid:
            with self.subTest(assignments=str(assignments[:1])), self.assertRaises(ValueError):
                route_to_profiles(profiles, assignments)

    def test_multi_server_library_checks_are_isolated(self):
        from bulkrr_servers import route_to_profiles, check_routed_libraries
        profiles = [{"id": "one", "kind": "sonarr", "url": "http://one:8989"},
                    {"id": "two", "kind": "sonarr", "url": "http://two:8989"}]
        routes = route_to_profiles(profiles, [
            {"item_id": 1, "kind": "sonarr", "profile_id": "one"},
            {"item_id": 2, "kind": "sonarr", "profile_id": "two"},
        ])
        calls = []
        def fetch(profile):
            calls.append(profile["id"])
            if profile["id"] == "one":
                raise ConnectionError("Server unavailable")
            return [{"id": 42}]
        result = check_routed_libraries(routes, fetch)
        self.assertEqual(calls, ["one", "two"])
        self.assertIn("unavailable", result[0]["error"])
        self.assertIsNone(result[0]["library_count"])
        self.assertEqual(result[1]["library_count"], 1)
        self.assertIsNone(result[1]["error"])

    def test_multi_server_library_check_rejects_duplicate_groups(self):
        from bulkrr_servers import route_to_profiles, check_routed_libraries
        routes = route_to_profiles(
            [{"id": "one", "kind": "radarr", "url": "http://one:7878"}],
            [{"item_id": 1, "kind": "radarr", "profile_id": "one"}])
        with self.assertRaises(ValueError):
            check_routed_libraries(routes + routes, lambda _: [])

    def test_library_check_refuses_same_title_on_two_servers_before_requests(self):
        from bulkrr_servers import check_routed_libraries
        routes = [
            {"profile": {"id": "one", "kind": "sonarr", "url": "http://one:8989"},
             "item_ids": [1]},
            {"profile": {"id": "two", "kind": "sonarr", "url": "http://two:8989"},
             "item_ids": [1]},
        ]
        with self.assertRaisesRegex(ValueError, "multiple destinations"):
            check_routed_libraries(routes, lambda _: [])

    def test_library_check_enforces_global_title_limit(self):
        from bulkrr_servers import check_routed_libraries
        routes = [
            {"profile": {"id": "one", "kind": "sonarr", "url": "http://one:8989"},
             "item_ids": list(range(1, 302))},
            {"profile": {"id": "two", "kind": "sonarr", "url": "http://two:8989"},
             "item_ids": list(range(302, 502))},
        ]
        with self.assertRaisesRegex(ValueError, "500 titles"):
            check_routed_libraries(routes, lambda _: [])

    def test_routed_import_plan_keeps_per_server_destinations_separate(self):
        from bulkrr_servers import plan_routed_imports
        profiles = [{"id": "anime", "kind": "sonarr", "url": "http://anime:8989"},
                    {"id": "movies", "kind": "radarr", "url": "http://movies:7878"}]
        assignments = [{"item_id": 1, "kind": "sonarr", "profile_id": "anime"},
                       {"item_id": 2, "kind": "radarr", "profile_id": "movies"}]
        settings = {
            "anime": {"quality_profile_id": 3, "root_folders": {"tv": "/tv", "anime": "/anime"}},
            "movies": {"quality_profile_id": 7, "root_folders": {"movie": "/movies"}},
        }
        plan = plan_routed_imports(profiles, assignments, settings)
        self.assertEqual(plan[0]["root_folders"]["anime"], "/anime")
        self.assertEqual(plan[1]["quality_profile_id"], 7)
        self.assertNotIn("key", str(plan))

    def test_routed_import_plan_refuses_missing_server_settings(self):
        from bulkrr_servers import plan_routed_imports
        profiles = [{"id": "anime", "kind": "sonarr", "url": "http://anime:8989"}]
        assignments = [{"item_id": 1, "kind": "sonarr", "profile_id": "anime"}]
        with self.assertRaisesRegex(ValueError, "Missing settings"):
            plan_routed_imports(profiles, assignments, {})
        with self.assertRaisesRegex(ValueError, "root folder"):
            plan_routed_imports(profiles, assignments, {
                "anime": {"quality_profile_id": 1, "root_folders": {"tv": "/tv"}}})

    def test_prepare_routed_import_batches_use_destination_specific_folders(self):
        from bulkrr_servers import prepare_routed_import_batches
        plans = [{"profile": {"id": "one", "kind": "sonarr", "url": "http://one:8989"},
                  "item_ids": [1], "quality_profile_id": 3,
                  "root_folders": {"tv": "/tv", "anime": "/anime"}},
                 {"profile": {"id": "two", "kind": "radarr", "url": "http://two:7878"},
                  "item_ids": [2], "quality_profile_id": 7,
                  "root_folders": {"movie": "/movies"}}]
        items = [{"selected": 0, "matches": [{"app": "sonarr", "type": "anime",
                  "id": 11, "data": {"title": "Anime"}}]},
                 {"selected": 0, "matches": [{"app": "radarr", "type": "movie",
                  "id": 22, "data": {"title": "Movie"}}]}]
        batches = prepare_routed_import_batches(plans, items)
        self.assertEqual(batches[0]["items"][0]["payload"]["rootFolderPath"], "/anime")
        self.assertEqual(batches[1]["items"][0]["payload"]["qualityProfileId"], 7)
        self.assertNotIn("rootFolderPath", items[0]["matches"][0]["data"])

    def test_prepare_routed_import_batches_rejects_unreviewed_title(self):
        from bulkrr_servers import prepare_routed_import_batches
        plans = [{"profile": {"id": "one", "kind": "sonarr", "url": "http://one:8989"},
                  "item_ids": [1], "quality_profile_id": 3,
                  "root_folders": {"tv": "/tv", "anime": "/anime"}}]
        with self.assertRaisesRegex(ValueError, "explicit metadata"):
            prepare_routed_import_batches(plans, [{"matches": [], "selected": -1}])

    def test_routed_batch_preview_detects_duplicates_without_writes(self):
        from bulkrr_servers import preview_routed_import_batches
        batches = [{"profile": {"id": "movies", "kind": "radarr", "url": "http://movies:7878"},
                    "items": [{"item_id": 1, "metadata_id": 99,
                               "duplicate_action": "skip",
                               "payload": {"title": "Film", "rootFolderPath": "/movies",
                                           "qualityProfileId": 3}}]}]
        calls = []
        def fetch(profile):
            calls.append(profile["id"])
            return [{"tmdbId": 99}]
        result = preview_routed_import_batches(batches, fetch)
        self.assertEqual(calls, ["movies"])
        self.assertEqual(result[0]["action"], "skip")
        self.assertTrue(result[0]["already_exists"])

    def test_routed_batch_preview_rejects_invalid_actions_before_fetch(self):
        from bulkrr_servers import preview_routed_import_batches
        batches = [{"profile": {"id": "movies", "kind": "radarr", "url": "http://movies:7878"},
                    "items": [{"item_id": 1, "metadata_id": 99,
                               "duplicate_action": "delete",
                               "payload": {"title": "Film", "rootFolderPath": "/movies",
                                           "qualityProfileId": 3}}]}]
        calls = []
        with self.assertRaisesRegex(ValueError, "duplicate action"):
            preview_routed_import_batches(batches, lambda profile: calls.append(profile))
        self.assertEqual(calls, [])

    def test_routed_add_execution_requires_explicit_approval(self):
        from bulkrr_servers import execute_routed_adds
        with self.assertRaises(PermissionError):
            execute_routed_adds([], lambda _: [], lambda *args: None)

    def test_routed_add_execution_skips_existing_and_isolates_destinations(self):
        from bulkrr_servers import execute_routed_adds
        def batch(name, ident):
            return {"profile": {"id": name, "kind": "radarr",
                                "url": "http://" + name + ":7878"},
                    "items": [{"item_id": ident, "metadata_id": ident,
                               "duplicate_action": "skip",
                               "payload": {"title": "Film " + str(ident),
                                           "rootFolderPath": "/movies",
                                           "qualityProfileId": 3}}]}
        batches = [batch("one", 1), batch("two", 2), batch("three", 3)]
        writes = []
        def fetch(profile):
            if profile["id"] == "three":
                raise ConnectionError("Offline")
            return [{"tmdbId": 1}] if profile["id"] == "one" else []
        def add(profile, endpoint, payload):
            writes.append((profile["id"], endpoint, payload))
        result = execute_routed_adds(batches, fetch, add, approved=True, search=False)
        self.assertEqual([entry["status"] for entry in result],
                         ["skipped", "added", "blocked"])
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][0:2], ("two", "movie"))
        self.assertFalse(writes[0][2]["addOptions"]["searchForMovie"])

    def test_routed_add_execution_rejects_bad_plan_before_writing(self):
        from bulkrr_servers import execute_routed_adds
        writes = []
        batch = {"profile": {"id": "one", "kind": "sonarr",
                             "url": "http://one:8989"},
                 "items": [{"item_id": 1, "metadata_id": 1,
                            "duplicate_action": "delete",
                            "payload": {"title": "Show", "rootFolderPath": "/tv",
                                        "qualityProfileId": 1}}]}
        with self.assertRaisesRegex(ValueError, "duplicate action"):
            execute_routed_adds([batch], lambda _: [],
                                lambda *args: writes.append(args), approved=True)
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
