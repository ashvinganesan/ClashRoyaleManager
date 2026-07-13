import datetime as dt
import importlib.util
import unittest

DISCORD_AVAILABLE = importlib.util.find_spec("discord") is not None

if DISCORD_AVAILABLE:
    from microbot.bot import build_enhanced_war_stats_embed


def clash_time(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.000Z")


def field_text(embed, *field_names: str) -> str:
    return "\n".join(field.value for field in embed.fields if field.name in field_names)


@unittest.skipUnless(DISCORD_AVAILABLE, "discord.py is not installed")
class MicrobotWarStatsTests(unittest.TestCase):
    def test_kick_demotion_requires_low_current_and_low_or_missing_average(self):
        now = dt.datetime.now(dt.timezone.utc)
        first_seen = (now - dt.timedelta(days=70)).isoformat()

        current_participants = [
            {"tag": "#HIGHAVG", "name": "Nameyguy", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
            {"tag": "#KING", "name": "KING AJ", "fame": 1900, "decksUsedToday": 0, "decksUsed": 0},
            {"tag": "#HIGHCURRENT", "name": "Metro Franky", "fame": 2300, "decksUsedToday": 0, "decksUsed": 0},
            {"tag": "#LOWBOTH", "name": "diell", "fame": 1400, "decksUsedToday": 0, "decksUsed": 0},
            {"tag": "#NOAVG", "name": "Code name: ????", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
        ]
        members_payload = {
            "items": [
                {"tag": "#HIGHAVG", "name": "Nameyguy", "role": "member"},
                {"tag": "#KING", "name": "KING AJ", "role": "elder"},
                {"tag": "#HIGHCURRENT", "name": "Metro Franky", "role": "coLeader"},
                {"tag": "#LOWBOTH", "name": "diell", "role": "member"},
                {"tag": "#NOAVG", "name": "Code name: ????", "role": "leader"},
            ]
        }
        scores_by_tag = {
            "#HIGHAVG": [2320, 2320, 2320, 2320, 2320],
            "#KING": [2200, 2200, 2200, 2200, 2200],
            "#HIGHCURRENT": [1400, 1400],
            "#LOWBOTH": [1510, 1510, 1510, 1510, 1510],
        }
        race_log_items = []

        for index in range(5):
            participants = []

            for tag, scores in scores_by_tag.items():
                if index < len(scores):
                    name = next(item["name"] for item in current_participants if item["tag"] == tag)
                    participants.append({"tag": tag, "name": name, "fame": scores[index]})

            race_log_items.append(
                {
                    "createdDate": clash_time(now - dt.timedelta(days=7 * (index + 1))),
                    "standings": [{"clan": {"tag": "#CLAN", "participants": participants}}],
                }
            )

        embed = build_enhanced_war_stats_embed(
            {"periodIndex": 6, "clan": {"name": "A Clan Reborn", "tag": "#CLAN", "participants": current_participants}},
            members_payload,
            {"items": race_log_items},
            {participant["tag"]: {"first_seen_at": first_seen} for participant in current_participants},
            2000,
            2500,
        )

        kick_text = field_text(embed, "Suggested Kick/Demotion", "More Candidates")
        leaders_text = field_text(embed, "Rolling 35-Day Leaders")

        self.assertIn("🟫 Member diell", kick_text)
        self.assertIn("🟥 Leader Code name: ????", kick_text)
        self.assertNotIn("Nameyguy", kick_text)
        self.assertNotIn("KING AJ", kick_text)
        self.assertNotIn("Metro Franky", kick_text)
        self.assertIn("🟩 Elder KING AJ", leaders_text)
        self.assertIn("🟥 Co-leader Metro Franky", leaders_text)


if __name__ == "__main__":
    unittest.main()
