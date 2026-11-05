import json
import os
import re
import unittest


def jload(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

from _load import ROOT

SKILLS = ["trader-copycat", "trader-news", "trader-budget", "trader-insider", "trader-analyst",
          "trader-screener", "trader-risk", "trader-broker", "trader-tax", "trader-alerts",
          "trader-rebalance"]
SCRIPTS = {"trader-copycat": "copycat.py", "trader-news": "news.py", "trader-budget": "size.py",
           "trader-insider": "insider.py", "trader-analyst": "facts.py", "trader-screener": "screen.py",
           "trader-risk": "check.py", "trader-broker": "ticket.py", "trader-tax": "lots.py",
           "trader-alerts": "alerts.py", "trader-rebalance": "rebalance.py"}
SECRETS = re.compile(r"(eyJ[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|"
                     r"GROWW_(API_KEY|API_SECRET|TOTP_SECRET)\s*=\s*['\"][A-Za-z0-9]{12,})")


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


class Repo(unittest.TestCase):
    def test_eleven_skills_with_frontmatter(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s" % s, fm, s)
            self.assertRegex(fm, r"description: >-\n  \S", s)
            self.assertIn(SCRIPTS[s], text, "%s SKILL.md must mention its script" % s)
            self.assertIn("${CLAUDE_SKILL_DIR}", text, s)
            self.assertTrue(os.path.exists(os.path.join(ROOT, s, SCRIPTS[s])), s)

    def test_every_skill_has_safety_and_not_advice(self):
        for s in SKILLS:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("## Safety", text, s)
            self.assertRegex(text, r"[Nn]ot (financial|tax) advice", s)

    def test_only_broker_mentions_place_order_call(self):
        for s in SKILLS:
            if s == "trader-broker":
                continue
            with open(os.path.join(ROOT, s, SCRIPTS[s]), encoding="utf-8") as fh:
                code = fh.read()
            self.assertNotIn(".place_order(", code, s)
            self.assertNotIn("growwapi", code, s)

    def test_manifests(self):
        plugin = jload(os.path.join(ROOT, ".claude-plugin", "plugin.json"))
        market = jload(os.path.join(ROOT, ".claude-plugin", "marketplace.json"))
        self.assertEqual(plugin["name"], "bharat-trader-skill")
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        self.assertEqual(plugin["license"], "MIT")

    def test_readme_lists_every_skill(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        for s in SKILLS:
            self.assertIn("/%s" % s, readme, s)

    def test_paper_is_default(self):
        cfg = jload(os.path.join(ROOT, "trader-budget", "config.example.json"))
        self.assertIs(cfg["paper"], True)
        for k in ("allow_intraday", "allow_fno", "allow_mtf", "allow_short"):
            self.assertIs(cfg[k], False, k)

    def test_no_secrets_committed(self):
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "fixtures")]
            for f in files:
                if f.endswith((".py", ".md", ".json", ".sh", ".txt")):
                    with open(os.path.join(base, f), encoding="utf-8", errors="ignore") as fh:
                        self.assertIsNone(SECRETS.search(fh.read()), os.path.join(base, f))


if __name__ == "__main__":
    unittest.main()
