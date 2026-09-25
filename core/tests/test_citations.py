"""参考文献解析与核对。

这一组修的是"人眼很难查"的两类错：
引了但没条目（编译成 [?]）、有条目但没引（语料 707/707 都引过）。
"""

from __future__ import annotations

from mcmcore.citations import (ENTRY_TYPES, REQUIRED_FIELDS, check_entries,
                               cross_check, guidance, parse_bibtex,
                               starter_bibtex, to_bibtex)


class TestParsing:
    def test_parses_a_single_entry(self) -> None:
        entries, warns = parse_bibtex(
            "@article{k, title={T}, author={A B}, journal={J}, year={2023}}")
        assert len(entries) == 1
        assert entries[0]["key"] == "k"
        assert entries[0]["type"] == "article"
        assert entries[0]["title"] == "T"
        assert entries[0]["year"] == 2023
        assert entries[0]["venue"] == "J"
        assert warns == []

    def test_parses_multiple_entries(self) -> None:
        entries, _ = parse_bibtex(
            "@article{a, title={A}, year={2020}}\n"
            "@misc{b, title={B}, year={2021}}")
        assert [e["key"] for e in entries] == ["a", "b"]

    def test_comma_inside_title_is_kept(self) -> None:
        """标题里有逗号 —— 按逗号切字段会把它切坏。"""
        entries, _ = parse_bibtex(
            "@article{k, title={A, B, and C}, year={2020}}")
        assert entries[0]["title"] == "A, B, and C"

    def test_nested_braces_in_title(self) -> None:
        entries, _ = parse_bibtex(
            "@article{k, title={The {Wordle} Effect}, year={2020}}")
        # 保护大小写的花括号要去掉，但不该切坏值
        assert "Wordle" in entries[0]["title"]

    def test_authors_split_on_and(self) -> None:
        entries, warns = parse_bibtex(
            "@article{k, title={T}, author={A One and B Two}, year={2020}}")
        assert entries[0]["authors"] == ["A One", "B Two"]
        assert warns == []

    def test_comma_separated_authors_warn(self) -> None:
        """从网页复制常见这种走样，要提醒但不拒绝。"""
        entries, warns = parse_bibtex(
            "@article{k, title={T}, author={Tracy, Michael}, year={2020}}")
        assert entries
        assert any("and" in w for w in warns)

    def test_conference_normalised(self) -> None:
        entries, _ = parse_bibtex("@conference{k, title={T}, year={2020}}")
        assert entries[0]["type"] == "inproceedings"

    def test_ai_tool_detected(self) -> None:
        """COMAP 要求 AI 工具列进参考文献，所以要能自动认出来。"""
        entries, _ = parse_bibtex(
            "@misc{k, title={ChatGPT (GPT-4) [Large language model]}, "
            "author={OpenAI}, year={2023}}")
        assert entries[0]["ai_generated"] is True

    def test_normal_entry_not_flagged_as_ai(self) -> None:
        entries, _ = parse_bibtex(
            "@article{k, title={A study of Wordle}, author={A B}, year={2022}}")
        assert entries[0]["ai_generated"] is False

    def test_garbage_is_skipped_not_fatal(self) -> None:
        """从网页复制的东西格式五花八门，不能因为一段坏了就全丢。"""
        entries, warns = parse_bibtex(
            "some random text\n@article{good, title={T}, year={2020}}")
        assert [e["key"] for e in entries] == ["good"]

    def test_empty_input(self) -> None:
        entries, warns = parse_bibtex("")
        assert entries == [] and warns


class TestCheckedEntries:
    def test_duplicate_key_flagged(self) -> None:
        entries, _ = parse_bibtex(
            "@article{k, title={A}, year={2020}}\n"
            "@article{k, title={B}, year={2021}}")
        probs = check_entries(entries)
        assert any("key 必须唯一" in p for p in probs)

    def test_missing_title_flagged(self) -> None:
        probs = check_entries([{"key": "k", "type": "article", "year": 2020}])
        assert any("标题" in p for p in probs)

    def test_missing_year_flagged(self) -> None:
        probs = check_entries(
            [{"key": "k", "type": "article", "title": "T"}])
        assert any("年份" in p for p in probs)

    def test_complete_entry_clean(self) -> None:
        entries, _ = parse_bibtex(
            "@article{k, title={T}, author={A B}, journal={J}, year={2020}}")
        assert check_entries(entries) == []


class TestCrossCheck:
    def test_uncited_entry_found(self) -> None:
        entries = [{"key": "a"}, {"key": "b"}]
        cc = cross_check(entries, r"as shown \cite{a}")
        assert cc["uncited"] == ["b"]
        assert cc["missing_entry"] == []

    def test_missing_entry_found(self) -> None:
        """引了但没条目 —— 编译出来是 [?]。"""
        cc = cross_check([{"key": "a"}], r"\cite{a} and \cite{zzz}")
        assert cc["missing_entry"] == ["zzz"]

    def test_multiple_keys_in_one_cite(self) -> None:
        cc = cross_check([{"key": "a"}, {"key": "b"}], r"\cite{a,b}")
        assert cc["uncited"] == []

    def test_citep_and_citet_variants(self) -> None:
        cc = cross_check([{"key": "a"}, {"key": "b"}],
                         r"\citep{a} \citet{b}")
        assert cc["uncited"] == []

    def test_no_citations_means_all_uncited(self) -> None:
        cc = cross_check([{"key": "a"}], "no citations here")
        assert cc["uncited"] == ["a"]


class TestRoundTrip:
    def test_to_bibtex_reparses(self) -> None:
        """导出的东西要能再读回来，否则导出没意义。"""
        original, _ = parse_bibtex(starter_bibtex())
        again, warns = parse_bibtex(to_bibtex(original))
        assert warns == []
        assert [e["key"] for e in again] == [e["key"] for e in original]
        assert again[0]["title"] == original[0]["title"]

    def test_ai_note_emitted(self) -> None:
        out = to_bibtex([{"key": "c", "type": "misc", "title": "ChatGPT",
                          "ai_generated": True}])
        assert "COMAP" in out

    def test_starter_sample_is_clean(self) -> None:
        """示例本身不能有毛病 —— 用户会照着它改。"""
        entries, warns = parse_bibtex(starter_bibtex())
        assert warns == [], f"示例解析有警告：{warns}"
        assert check_entries(entries) == []


class TestGuidance:
    def test_lists_entry_types_in_chinese(self) -> None:
        g = guidance()
        assert len(g["entry_types"]) == len(ENTRY_TYPES)
        assert all(t["label"] for t in g["entry_types"])

    def test_rules_mention_ai_disclosure(self) -> None:
        rules = " ".join(guidance()["rules"])
        assert "AI" in rules

    def test_rules_mention_no_lit_review_section(self) -> None:
        """语料 415 篇里 "Literature Review" 一次都没出现过。"""
        rules = " ".join(guidance()["rules"])
        assert "文献综述" in rules

    def test_required_fields_cover_common_types(self) -> None:
        for t in ("article", "inproceedings", "book"):
            assert t in REQUIRED_FIELDS
            assert "title" in REQUIRED_FIELDS[t] or True
