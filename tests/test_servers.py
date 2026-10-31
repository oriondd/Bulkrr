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

    def test_saved_profiles_have_no_key(self):
        profiles = public_profiles([{"id": "one", "kind": "radarr", "url": "http://host", "key": "secret"}])
        self.assertNotIn("key", profiles[0])


if __name__ == "__main__":
    unittest.main()
