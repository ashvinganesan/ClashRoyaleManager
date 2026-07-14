import datetime as dt
import importlib.util
import unittest

DISCORD_AVAILABLE = importlib.util.find_spec("discord") is not None

if DISCORD_AVAILABLE:
    from microbot.bot import (
        build_enhanced_war_stats_embed,
        build_last_war_bottom_embed,
        build_player_war_stats_embed,
        collect_completed_war_stats,
        resolve_war_player,
        war_player_index,
    )


def clash_time(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.000Z")


def field_text(embed, *field_names: str) -> str:
    return "\n".join(field.value for field in embed.fields if field.name in field_names)


@unittest.skipUnless(DISCORD_AVAILABLE, "discord.py is not installed")
class MicrobotWarStatsTests(unittest.TestCase):
    def test_kick_demotion_requires_low_current_and_low_or_missing_average(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
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
            {
                participant["tag"]: {
                    "first_seen_at": first_seen,
                    "manual_joined_at": (
                        dt.datetime(2025, 1, 14, tzinfo=dt.timezone.utc).isoformat()
                        if participant["tag"] == "#KING"
                        else None
                    ),
                }
                for participant in current_participants
            },
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
        self.assertIn("joined Jan 14", leaders_text)
        self.assertIn("🟥 Co-leader Metro Franky", leaders_text)

    def test_training_period_uses_last_full_war_and_skips_partial_scores(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        last_completed = now - dt.timedelta(hours=2)
        previous_completed = last_completed - dt.timedelta(days=7)
        full_first_seen = (last_completed - dt.timedelta(days=4)).isoformat()
        old_first_seen = (last_completed - dt.timedelta(days=21)).isoformat()
        recent_first_seen = (last_completed - dt.timedelta(days=1)).isoformat()

        current_participants = [
            {"tag": "#GOOD", "name": "krazz tony", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
            {"tag": "#LOW", "name": "ShouldKick", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
            {"tag": "#FRESH", "name": "Fresh Join", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
        ]
        members_payload = {
            "items": [
                {"tag": "#GOOD", "name": "krazz tony", "role": "member"},
                {"tag": "#LOW", "name": "ShouldKick", "role": "member"},
                {"tag": "#FRESH", "name": "Fresh Join", "role": "elder"},
            ]
        }
        race = {
            "periodType": "training",
            "periodIndex": 0,
            "clan": {"name": "A Clan Reborn", "tag": "#CLAN", "participants": current_participants},
        }
        race_log = {
            "items": [
                {
                    "createdDate": clash_time(last_completed),
                    "standings": [
                        {
                            "clan": {
                                "tag": "#CLAN",
                                "participants": [
                                    {"tag": "#GOOD", "name": "krazz tony", "fame": 2600},
                                    {"tag": "#LOW", "name": "ShouldKick", "fame": 0},
                                    {"tag": "#FRESH", "name": "Fresh Join", "fame": 700},
                                ],
                            }
                        }
                    ],
                },
                {
                    "createdDate": clash_time(previous_completed),
                    "standings": [
                        {
                            "clan": {
                                "tag": "#CLAN",
                                "participants": [
                                    {"tag": "#GOOD", "name": "krazz tony", "fame": 1000},
                                    {"tag": "#LOW", "name": "ShouldKick", "fame": 1300},
                                ],
                            }
                        }
                    ],
                },
            ]
        }
        presence_map = {
            "#GOOD": {"first_seen_at": full_first_seen, "last_seen_at": now.isoformat()},
            "#LOW": {"first_seen_at": old_first_seen, "last_seen_at": now.isoformat()},
            "#FRESH": {"first_seen_at": recent_first_seen, "last_seen_at": now.isoformat()},
        }

        embed = build_enhanced_war_stats_embed(
            race,
            members_payload,
            race_log,
            presence_map,
            2000,
            2500,
        )

        summary = field_text(embed, "Training Period")
        kick_text = field_text(embed, "Suggested Kick/Demotion", "More Candidates")

        self.assertIn("Last war fame: **3,300**", summary)
        self.assertIn("Decks today: **0/200 training decks used**", summary)
        self.assertIn("🟫 Member ShouldKick - 0 last war", kick_text)
        self.assertNotIn("krazz tony", kick_text)
        self.assertNotIn("Fresh Join", kick_text)

        historical_stats, _ = collect_completed_war_stats(race_log, "#CLAN", now - dt.timedelta(days=35))
        players_by_tag = war_player_index(members_payload, race, historical_stats)
        player_embed = build_player_war_stats_embed(
            players_by_tag["#GOOD"],
            race,
            members_payload,
            race_log,
            presence_map,
            2000,
            2500,
        )
        player_current = field_text(player_embed, "Training Period / Last War")
        player_history = field_text(player_embed, "Rolling 35-Day Full-War History")
        player_recommendations = field_text(player_embed, "Recommendations")

        self.assertIn("Last war fame: **2,600**", player_current)
        self.assertIn("Average: **2,600** over **1** full completed wars", player_history)
        self.assertIn("partial; not counted", player_history)
        self.assertIn("Kick/Demotion: **No**", player_recommendations)

    def test_first_observed_high_score_counts_and_prevents_short_sample_kick(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        last_completed = now - dt.timedelta(hours=2)
        previous_completed = last_completed - dt.timedelta(days=7)
        first_seen = previous_completed.isoformat()

        current_participants = [
            {"tag": "#OUCH", "name": "OuchMyElbow", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
            {"tag": "#LOW", "name": "ConsistentLow", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
        ]
        members_payload = {
            "items": [
                {"tag": "#OUCH", "name": "OuchMyElbow", "role": "member"},
                {"tag": "#LOW", "name": "ConsistentLow", "role": "member"},
            ]
        }
        race = {
            "periodType": "training",
            "periodIndex": 0,
            "clan": {"name": "A Clan Reborn", "tag": "#CLAN", "participants": current_participants},
        }
        race_log = {
            "items": [
                {
                    "createdDate": clash_time(last_completed),
                    "standings": [
                        {
                            "clan": {
                                "tag": "#CLAN",
                                "participants": [
                                    {"tag": "#OUCH", "name": "OuchMyElbow", "fame": 700},
                                    {"tag": "#LOW", "name": "ConsistentLow", "fame": 700},
                                ],
                            }
                        }
                    ],
                },
                {
                    "createdDate": clash_time(previous_completed),
                    "standings": [
                        {
                            "clan": {
                                "tag": "#CLAN",
                                "participants": [
                                    {"tag": "#OUCH", "name": "OuchMyElbow", "fame": 3050},
                                    {"tag": "#LOW", "name": "ConsistentLow", "fame": 700},
                                ],
                            }
                        }
                    ],
                },
            ]
        }
        presence_map = {
            "#OUCH": {
                "first_seen_at": first_seen,
                "first_seen_source": "river race log",
                "last_seen_at": now.isoformat(),
            },
            "#LOW": {
                "first_seen_at": first_seen,
                "first_seen_source": "river race log",
                "last_seen_at": now.isoformat(),
            },
        }

        embed = build_enhanced_war_stats_embed(
            race,
            members_payload,
            race_log,
            presence_map,
            2000,
            2500,
        )
        kick_text = field_text(embed, "Suggested Kick/Demotion", "More Candidates")

        self.assertNotIn("OuchMyElbow", kick_text)
        self.assertIn("ConsistentLow", kick_text)

        historical_stats, _ = collect_completed_war_stats(race_log, "#CLAN", now - dt.timedelta(days=35))
        players_by_tag = war_player_index(members_payload, race, historical_stats)
        player_embed = build_player_war_stats_embed(
            players_by_tag["#OUCH"],
            race,
            members_payload,
            race_log,
            presence_map,
            2000,
            2500,
        )
        player_history = field_text(player_embed, "Rolling 35-Day Full-War History")
        player_recommendations = field_text(player_embed, "Recommendations")

        self.assertIn("Average: **1,875** over **2** full completed wars", player_history)
        self.assertNotIn("partial; not counted", player_history)
        self.assertIn("Kick/Demotion: **No**", player_recommendations)
        self.assertIn("short history includes a 2,000+ full war", player_recommendations)

    def test_last_war_bottom_ranks_include_departed_players(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        last_completed = now - dt.timedelta(days=1)
        previous_completed = last_completed - dt.timedelta(days=7)
        first_seen = (last_completed - dt.timedelta(days=30)).isoformat()
        last_seen = now.isoformat()

        last_war_participants = [
            {"tag": f"#P{index}", "name": f"Player {index}", "fame": 5000 - index}
            for index in range(1, 41)
        ]
        last_war_participants.extend(
            [
                {"tag": "#LOWIN", "name": "Low In", "fame": 1200},
                {"tag": "#GONE", "name": "Gone Guy", "fame": 0},
            ]
        )
        current_participants = [
            {"tag": "#LOWIN", "name": "Low In", "fame": 0, "decksUsedToday": 0, "decksUsed": 0},
        ]
        members_payload = {
            "items": [
                {"tag": "#LOWIN", "name": "Low In", "role": "member"},
            ]
        }
        race = {
            "periodType": "training",
            "periodIndex": 0,
            "clan": {"name": "A Clan Reborn", "tag": "#CLAN", "participants": current_participants},
        }
        race_log = {
            "items": [
                {
                    "createdDate": clash_time(last_completed),
                    "standings": [{"clan": {"tag": "#CLAN", "participants": last_war_participants}}],
                },
                {
                    "createdDate": clash_time(previous_completed),
                    "standings": [
                        {
                            "clan": {
                                "tag": "#CLAN",
                                "participants": [
                                    {"tag": "#LOWIN", "name": "Low In", "fame": 1800},
                                    {"tag": "#GONE", "name": "Gone Guy", "fame": 1300},
                                ],
                            }
                        }
                    ],
                },
            ]
        }
        presence_map = {
            "#LOWIN": {"first_seen_at": first_seen, "last_seen_at": last_seen},
            "#GONE": {"first_seen_at": first_seen, "last_seen_at": last_seen},
        }

        war_stats_embed = build_enhanced_war_stats_embed(
            race,
            members_payload,
            race_log,
            presence_map,
            2000,
            2500,
        )
        embed = build_last_war_bottom_embed(
            race,
            members_payload,
            race_log,
            presence_map,
        )

        bottom_text = field_text(embed, "Rank 41+ Players", "More Rank 41+")

        self.assertEqual("", field_text(war_stats_embed, "Last War Rank 41+", "Rank 41+ Players"))
        self.assertEqual(embed.title, "A Clan Reborn Last War Rank 41+")
        self.assertIn("41. 🟫 Member Low In - 1,200 last war, 1,500 avg/2 full wars", bottom_text)
        self.assertIn("status: in clan", bottom_text)
        self.assertIn("42. ⬜ Not in clan Gone Guy - 0 last war, 650 avg/2 full wars", bottom_text)
        self.assertIn("status: not in clan anymore", bottom_text)
        self.assertNotIn("Player 40", bottom_text)

        historical_stats, _ = collect_completed_war_stats(race_log, "#CLAN", now - dt.timedelta(days=35))
        players_by_tag = war_player_index(members_payload, race, historical_stats)
        player_embed = build_player_war_stats_embed(
            players_by_tag["#GONE"],
            race,
            members_payload,
            race_log,
            presence_map,
            2000,
            2500,
        )
        context = field_text(player_embed, "Clan Context")

        self.assertIn("not in current clan", player_embed.description)
        self.assertIn("In current roster: **No - not in clan anymore**", context)

    def test_player_stats_can_resolve_ign_and_show_recommendation(self):
        now = dt.datetime.now(dt.timezone.utc)
        first_seen = (now - dt.timedelta(days=21)).isoformat()
        tag = "#P2Y0R"
        race = {
            "periodIndex": 6,
            "clan": {
                "name": "A Clan Reborn",
                "tag": "#CLAN",
                "participants": [
                    {"tag": tag, "name": "DaddyRizz", "fame": 700, "decksUsedToday": 1, "decksUsed": 12},
                ],
            },
        }
        members_payload = {"items": [{"tag": tag, "name": "DaddyRizz", "role": "elder"}]}
        race_log = {
            "items": [
                {
                    "createdDate": clash_time(now - dt.timedelta(days=7)),
                    "standings": [{"clan": {"tag": "#CLAN", "participants": [{"tag": tag, "name": "DaddyRizz", "fame": 1850}]}}],
                },
                {
                    "createdDate": clash_time(now - dt.timedelta(days=14)),
                    "standings": [{"clan": {"tag": "#CLAN", "participants": [{"tag": tag, "name": "DaddyRizz", "fame": 1900}]}}],
                },
            ]
        }
        historical_stats, _ = collect_completed_war_stats(race_log, "#CLAN", now - dt.timedelta(days=35))
        players_by_tag = war_player_index(members_payload, race, historical_stats)

        target, error = resolve_war_player("DaddyRizz", players_by_tag)
        partial_target, partial_error = resolve_war_player("Daddy", players_by_tag)

        self.assertIsNone(error)
        self.assertIsNone(partial_error)
        self.assertEqual(target["tag"], tag)
        self.assertEqual(partial_target["tag"], tag)

        embed = build_player_war_stats_embed(
            target,
            race,
            members_payload,
            race_log,
            {tag: {"first_seen_at": first_seen, "last_seen_at": now.isoformat()}},
            2000,
            2500,
        )
        recommendations = field_text(embed, "Recommendations")
        history = field_text(embed, "Rolling 35-Day Full-War History")

        self.assertEqual(embed.title, "DaddyRizz War Stats")
        self.assertIn("🟩 Elder", embed.description)
        self.assertIn("Average: **1,875**", history)
        self.assertIn("Kick/Demotion: **Yes**", recommendations)


if __name__ == "__main__":
    unittest.main()
