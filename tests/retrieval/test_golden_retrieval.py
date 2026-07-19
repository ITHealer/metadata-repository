"""Golden lexical retrieval smoke test for approved semantic chunks."""

import os
from pathlib import Path

from metadata_pipeline.application.retrieval_evaluation import (
    evaluate_retrieval,
    load_golden_questions,
    write_retrieval_report,
)
from metadata_pipeline.domain.published import Chunk

QUESTIONS = Path("tests/fixtures/golden_questions.yml")


def test_top_three_document_rate_and_required_facts(
    approved_chunks: tuple[Chunk, ...],
) -> None:
    questions = load_golden_questions(QUESTIONS)
    report = evaluate_retrieval(approved_chunks, questions, top_k=3)

    report_path = os.environ.get("RETRIEVAL_REPORT")
    if report_path:
        write_retrieval_report(Path(report_path), report)

    assert len(questions) >= 10
    assert report.document_hit_rate >= 0.9
    assert report.passed, {
        result.question_id: result.missing_facts
        for result in report.results
        if not result.document_found or result.missing_facts
    }
