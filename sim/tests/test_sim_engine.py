from mandos_sim import Sanitizer, SimEngine, build_node_prompt, validate_screenplay


def synthetic_screenplay():
    return {
        "scenario_id": "SYNTH-TEST",
        "version": "test",
        "title": "Synthetic CI scenario",
        "location": "Acme County",
        "date": "May 1 2026",
        "facility": "Acme Plant",
        "physics_rules": [],
        "characters": [{"name": "Operator A", "role": "outside operator"}],
        "documents_available": [],
        "nodes": [
            {
                "node_id": "N1",
                "timestamp_offset_hours": 0,
                "title": "Rising pressure",
                "situation_briefing": "At Acme Plant on May 1 2026, Operator A sees rising pressure.",
                "physical_state": {"pressure": "10 psi", "temperature": "220°F"},
                "sociotechnical_state": {},
                "information_operator_has": [],
                "information_operator_lacks": [],
                "actions_available": [
                    {
                        "action_id": "N1-A",
                        "description": "Stop work and consult the domain expert.",
                        "how_to_invoke": "Call the expert and halt the lineup.",
                        "sim_response": "The lineup is halted and reviewed.",
                        "state_change": {"expert_consulted": True},
                        "consequence_trajectory": "prevention",
                    },
                    {
                        "action_id": "N1-B",
                        "description": "Continue the lineup.",
                        "how_to_invoke": "Proceed without consultation.",
                        "sim_response": "The lineup continues.",
                        "state_change": {},
                        "consequence_trajectory": "continuation",
                    },
                ],
                "optimal_action": "N1-A",
                "actual_action_taken": "N1-B",
                "hard_gate": False,
                "if_optimal_next_node": "PREVENTED",
                "if_actual_next_node": "HISTORICAL_OUTCOME",
            }
        ],
        "scoring_rubric": {},
        "terminal_conditions": {
            "prevention": {"output_message": "Acme Plant was stabilized by Operator A."},
            "partial_mitigation": {"output_message": "Acme Plant was partially stabilized."},
            "historical_outcome": {"output_message": "Operator A was named in the historical outcome at Acme Plant."},
            "escalation": {"output_message": "Acme Plant escalated."},
        },
    }


def synthetic_sanitization_map():
    return {
        "sanitization_map": {
            "identifiers": {
                "facility": {"json_value": "Acme Plant", "operator_sees": "the facility"},
                "date": {"json_value": "May 1 2026", "operator_sees": None},
            },
            "characters": [{"json_name": "Operator A", "operator_sees": "the operator"}],
        }
    }


def test_synthetic_screenplay_validates_and_sanitizes():
    screenplay = synthetic_screenplay()
    sanitizer = Sanitizer(synthetic_sanitization_map())

    assert validate_screenplay(screenplay) == []

    prompt = build_node_prompt(screenplay["nodes"][0], sanitizer)
    assert "the facility" in prompt
    assert "the operator" in prompt
    assert "10 psi" in prompt
    assert "220°F" in prompt
    assert "Acme Plant" not in prompt
    assert "May 1 2026" not in prompt


def test_historical_outcome_is_the_only_terminal_bypass():
    screenplay = synthetic_screenplay()
    sanitizer = Sanitizer(synthetic_sanitization_map())

    prevention = sanitizer.emit_terminal_outcome("prevention", screenplay["terminal_conditions"]["prevention"])
    historical = sanitizer.emit_terminal_outcome("historical_outcome", screenplay["terminal_conditions"]["historical_outcome"])

    assert "Acme Plant" not in prevention
    assert "Operator A" not in prevention
    assert "Operator A" in historical
    assert "Acme Plant" in historical


def test_mock_engine_reaches_prevention_without_api_keys():
    screenplay = synthetic_screenplay()
    sanitizer = Sanitizer(synthetic_sanitization_map())
    config = {
        "model_provider": "anthropic",
        "model_id": "mock-model",
        "model_shortname": "mock",
        "temperature": 0.0,
        "max_tokens": 200,
    }

    log = SimEngine(screenplay, sanitizer, config, mock=True).run()

    assert log.outcome == "prevention"
    assert len(log.nodes) == 1
    assert log.expert_consulted is True
    assert log.first_intervention_node == "N1"
