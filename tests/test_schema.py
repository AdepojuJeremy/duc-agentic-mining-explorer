from duc_agentic_mining.models import CandidateValidation, ProposalReview, VignetteProposal


def test_structured_models_forbid_extra_fields():
    for model in (CandidateValidation, VignetteProposal, ProposalReview):
        schema = model.model_json_schema()
        assert schema.get("additionalProperties") is False
