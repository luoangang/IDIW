from crawler_platform.package_help import data_profile, help_for


def test_data_profiles_cover_metadata_and_pdf():
    magetech = data_profile("magetech_journals")
    assert magetech["pdf_tag"] == "PDF链接"
    assert "摘要" in magetech["meta_tag"]
    custom = data_profile("custom_toc_journals")
    assert custom["meta_tag"].startswith("HTML/JSON")
    assert custom["pdf_tag"] == "无PDF"
    assert data_profile("missing-package") == {}


def test_core_package_help_is_available():
    assert "当期" in help_for("custom_toc_journals")
    assert "OpenAlex" in help_for("supplement_journals")
    assert help_for("custom_toc_journals") != help_for("magetech_journals")
    assert help_for("missing-package") == ""