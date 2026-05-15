from __future__ import annotations

from dataclasses import dataclass

from src.agents.classification_agent import ClassificationAgent
from src.agents.filing_agent import FilingAgent
from src.agents.ingest_agent import IngestAgent
from src.agents.learning_agent import LearningAgent
from src.agents.relationship_agent import RelationshipAgent
from src.agents.response_agent import ResponseAgent
from src.models.email_models import Classification, ClassificationInput
from src.models.filing_models import FilingDecision, FilingRule


@dataclass(frozen=True)
class EmailSupervisor:
    ingest_agent: IngestAgent
    classification_agent: ClassificationAgent
    relationship_agent: RelationshipAgent
    filing_agent: FilingAgent
    response_agent: ResponseAgent
    learning_agent: LearningAgent

    @classmethod
    def default(cls) -> EmailSupervisor:
        return cls(
            ingest_agent=IngestAgent(),
            classification_agent=ClassificationAgent(),
            relationship_agent=RelationshipAgent(),
            filing_agent=FilingAgent(),
            response_agent=ResponseAgent(),
            learning_agent=LearningAgent(),
        )

    def classify(self, item: ClassificationInput) -> Classification:
        return self.classification_agent.run(item)

    def propose_filing(
        self,
        classification: Classification,
        rules: list[FilingRule],
    ) -> FilingDecision:
        return self.filing_agent.run(classification, rules)
