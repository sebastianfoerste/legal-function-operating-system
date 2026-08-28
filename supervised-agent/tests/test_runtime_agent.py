from runtime_agent.app import SERVICE_NAME


def test_runtime_service_name_is_legal_ops_scoped():
    assert SERVICE_NAME == "legal_ops_agent_runtime"
