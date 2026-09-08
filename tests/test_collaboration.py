from jarvis.collaboration import CollaborativeWorkbench
from jarvis.schemas import RiskLevel
from jarvis.tools.registry import ToolRegistry


def test_collaborative_start_is_distinct_from_execution():
    assert CollaborativeWorkbench.looks_like_start(
        "Jarvis, vamos criar uma campanha no Google Ads"
    )
    assert not CollaborativeWorkbench._explicit_create(
        "Jarvis, vamos criar uma campanha no Google Ads"
    )
    assert CollaborativeWorkbench._explicit_create("pode criar a campanha agora")


def test_campaign_normalization_for_visual_workspace():
    rows = [
        {
            "campaign": {"id": "123", "name": "Fuel Search", "status": "ENABLED"},
            "metrics": {
                "impressions": "1000",
                "clicks": "50",
                "costMicros": "125000000",
                "conversions": 4,
                "conversionsValue": 360,
            },
        }
    ]
    result = CollaborativeWorkbench._normalize_campaigns(rows)
    assert result[0]["id"] == "123"
    assert result[0]["clicks"] == 50
    assert result[0]["cost_brl"] == 125.0
    assert result[0]["conversions"] == 4.0


def test_keyword_normalization_preserves_mutation_resources():
    rows = [
        {
            "adGroup": {"name": "Grupo A", "resourceName": "customers/1/adGroups/2"},
            "adGroupCriterion": {
                "resourceName": "customers/1/adGroupCriteria/2~3",
                "status": "ENABLED",
                "keyword": {"text": "barra energética", "matchType": "PHRASE"},
            },
            "metrics": {"impressions": 20, "clicks": 2, "costMicros": 4000000},
        }
    ]
    result = CollaborativeWorkbench._normalize_keywords(rows)
    assert result[0]["text"] == "barra energética"
    assert result[0]["resource_name"].endswith("2~3")
    assert result[0]["ad_group_resource"].endswith("adGroups/2")


def test_workbench_tool_is_high_risk_and_never_globally_autonomous():
    registry = ToolRegistry()
    tool = registry.tools["google_ads.workbench"]
    assert tool.risk == RiskLevel.HIGH
    autonomous = {item["name"] for item in registry.autonomous_specs()}
    assert "google_ads.workbench" not in autonomous
    assert "google_ads.keywords" in autonomous
    assert "google_ads.replace_keyword" not in autonomous
