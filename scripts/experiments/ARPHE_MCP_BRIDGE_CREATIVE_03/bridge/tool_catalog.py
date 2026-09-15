EXPOSED_TOOL_NAMES = (
    "ping", "resolve_status", "create_safe_working_timeline", "get_feature_flags",
    "list_longform_media", "get_transcript_metadata", "get_transcript_chunk",
    "validate_longform_edit_plan", "apply_longform_edit_plan",
    "start_prepare_longform_audio", "get_longform_audio_job",
    "create_project", "set_current_project", "create_timeline", "set_current_timeline",
    "duplicate_timeline_version", "get_creative_status", "create_fusion_composition",
    "inspect_fusion_graph", "capture_timeline_frames",
    "add_brand_background", "add_logo", "add_image_asset", "add_video_background",
    "add_text_plus", "add_review_card", "create_review_sequence", "create_review_sequence_v2",
    "set_review_highlight",
    "add_end_card",
    "animate_card_entry", "animate_card_exit", "animate_review_stack",
    "apply_transition_preset", "retime_creative_duration", "save_project", "render_preview",
    "queue_longform_exports", "start_longform_exports",
)

FORBIDDEN_GENERIC_TOOLS = {
    "run_python", "run_shell", "delete_project", "delete_timeline",
    "add_fusion_node", "add_any_node", "set_any_fusion_property", "eval_fusion_script",
}
