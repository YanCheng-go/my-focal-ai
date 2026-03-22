"""Tests for skills.sh trending ingestion — HTML parsing and URL building."""

import json

from ainews.ingest.skillssh_trending import (
    _extract_audit_entries,
    _extract_initial_skills,
    _extract_official_owners,
    _skill_url,
)

# --- _skill_url ---


def test_skill_url_basic():
    assert _skill_url("anthropic", "claude-code") == ("https://skills.sh/anthropic/claude-code")


def test_skill_url_with_special_chars():
    assert _skill_url("user", "my-skill") == "https://skills.sh/user/my-skill"


# --- _extract_initial_skills ---


def _wrap_rsc_skills(skills: list[dict]) -> str:
    """Build minimal RSC payload with initialSkills data."""
    escaped = json.dumps(skills).replace('"', '\\"')
    return f'<script>self.__next_f.push([1,"initialSkills\\":{escaped}"])</script>'


def test_extract_initial_skills_single():
    skills = [{"name": "code-review", "source": "anthropic", "installs": 100}]
    html = _wrap_rsc_skills(skills)
    result = _extract_initial_skills(html)
    assert len(result) == 1
    assert result[0]["name"] == "code-review"
    assert result[0]["installs"] == 100


def test_extract_initial_skills_multiple():
    skills = [
        {"name": "skill-a", "source": "user1", "installs": 50},
        {"name": "skill-b", "source": "user2", "installs": 30},
    ]
    html = _wrap_rsc_skills(skills)
    result = _extract_initial_skills(html)
    assert len(result) == 2


def test_extract_initial_skills_empty_array():
    html = _wrap_rsc_skills([])
    result = _extract_initial_skills(html)
    assert result == []


def test_extract_initial_skills_no_data():
    html = "<html><body>No skills here</body></html>"
    result = _extract_initial_skills(html)
    assert result == []


def test_extract_initial_skills_malformed_json():
    html = 'initialSkills\\":[{broken json'
    result = _extract_initial_skills(html)
    assert result == []


# --- _extract_official_owners ---


def _wrap_rsc_owners(owners: list[dict]) -> str:
    """Build minimal RSC payload with owners data."""
    data = {"owners": owners}
    escaped = json.dumps(data).replace('"', '\\"')
    return f'<script>self.__next_f.push([1,"{escaped}"])</script>'


def test_extract_official_owners_single():
    owners = [{"owner": "anthropic", "repos": [{"totalInstalls": 500, "skills": []}]}]
    html = _wrap_rsc_owners(owners)
    result = _extract_official_owners(html)
    assert len(result) == 1
    assert result[0]["owner"] == "anthropic"


def test_extract_official_owners_no_data():
    html = "<html><body>nothing</body></html>"
    result = _extract_official_owners(html)
    assert result == []


def test_extract_official_owners_empty_list():
    html = _wrap_rsc_owners([])
    result = _extract_official_owners(html)
    assert result == []


# --- _extract_audit_entries ---


def _wrap_rsc_audits(entries: list[dict]) -> str:
    """Build minimal RSC payload with audit entries using escaped JSON format."""
    parts = []
    for e in entries:
        entry_str = (
            f'{{\\"rank\\":{e["rank"]},\\"source\\":\\"{e["source"]}\\",'
            f'\\"skillId\\":\\"{e["skillId"]}\\",\\"name\\":\\"{e["name"]}\\"'
        )
        if "gen" in e:
            entry_str += f',\\"agentTrustHub\\":{{\\"overall_risk_level\\":\\"{e["gen"]}\\"}}'
        if "socket_alerts" in e:
            alerts = ",".join(["{}" for _ in range(e["socket_alerts"])])
            entry_str += f',\\"socket\\":{{\\"alerts\\":[{alerts}]}}'
        if "snyk" in e:
            entry_str += f',\\"snyk\\":{{\\"overall_risk_level\\":\\"{e["snyk"]}\\"}}'
        entry_str += "}"
        parts.append(entry_str)

    joined = ",".join(parts)
    return f'initialRows\\":[{joined}]'


def test_extract_audit_entries_single():
    html = _wrap_rsc_audits(
        [
            {"rank": 1, "source": "anthropic", "skillId": "claude-code", "name": "Claude Code"},
        ]
    )
    result = _extract_audit_entries(html)
    assert len(result) == 1
    assert result[0]["rank"] == 1
    assert result[0]["source"] == "anthropic"
    assert result[0]["skillId"] == "claude-code"
    assert result[0]["name"] == "Claude Code"


def test_extract_audit_entries_with_gen():
    html = _wrap_rsc_audits(
        [
            {
                "rank": 1,
                "source": "user",
                "skillId": "sk1",
                "name": "Skill1",
                "gen": "low",
            },
        ]
    )
    result = _extract_audit_entries(html)
    assert result[0]["gen"] == "low"


def test_extract_audit_entries_with_socket():
    html = _wrap_rsc_audits(
        [
            {
                "rank": 1,
                "source": "user",
                "skillId": "sk1",
                "name": "Skill1",
                "socket_alerts": 3,
            },
        ]
    )
    result = _extract_audit_entries(html)
    assert result[0]["socket_alerts"] == 3


def test_extract_audit_entries_with_snyk():
    html = _wrap_rsc_audits(
        [
            {
                "rank": 1,
                "source": "user",
                "skillId": "sk1",
                "name": "Skill1",
                "snyk": "high",
            },
        ]
    )
    result = _extract_audit_entries(html)
    assert result[0]["snyk"] == "high"


def test_extract_audit_entries_multiple():
    html = _wrap_rsc_audits(
        [
            {"rank": 1, "source": "a", "skillId": "s1", "name": "S1"},
            {"rank": 2, "source": "b", "skillId": "s2", "name": "S2"},
        ]
    )
    result = _extract_audit_entries(html)
    assert len(result) == 2
    assert result[0]["rank"] == 1
    assert result[1]["rank"] == 2


def test_extract_audit_entries_no_data():
    html = "<html>nothing</html>"
    result = _extract_audit_entries(html)
    assert result == []
