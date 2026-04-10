package policy

const (
	ReasonAllowed           = "allowed"
	ReasonDeniedCommand     = "denied_command"
	ReasonProtectedPath     = "protected_path"
	ReasonOutOfScope        = "out_of_plan_scope"
	ReasonInjectionDetected = "injection_detected"
	ReasonStrictModeDefault = "strict_mode_default_deny"
	ReasonPathTraversal     = "path_traversal_attempt"
	ReasonUnknownOperation  = "unknown_operation"
)
