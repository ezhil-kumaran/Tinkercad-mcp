"""Centralized selectors and locator patterns for Tinkercad Circuits."""

from __future__ import annotations

# Auth selectors
AUTH_SELECTORS = {
    # Check if logged in
    "user_avatar": [
        "[data-testid='user-profile-menu']",
        "button[aria-label*='User Profile']",
        ".user-avatar",
        ".header__profile",
        "img[alt*='Avatar']",
        "button.avatar-button",
    ],
    # Check if on login or landing page
    "login_button": [
        "a[href*='/login']",
        "button:has-text('Log In')",
        "button:has-text('Sign In')",
        "a:has-text('Log In')",
    ],
    "join_button": [
        "a[href*='/join']",
        "button:has-text('Join now')",
        "button:has-text('Sign up')",
    ],
    # Autodesk login form inputs
    "email_input": [
        "input#userName",
        "input[name='userName']",
        "input#email",
        "input[type='email']",
        "input[name='email']",
    ],
    "next_button": [
        "button#btn-next",
        "button:has-text('Next')",
        "button:has-text('Continue')",
    ],
    "password_input": [
        "input#password",
        "input[name='password']",
        "input[type='password']",
    ],
    "signin_submit_button": [
        "button#btn-submit",
        "button:has-text('Sign In')",
        "button:has-text('Log In')",
    ],
    "logout_button": [
        "a[href*='/logout']",
        "button:has-text('Log Out')",
        "button:has-text('Sign Out')",
    ],
    "error_alert": [
        "#username-error",
        "#password-error",
        ".notification-error",
        ".alert-danger",
        "[role='alert']",
        ".error-message",
        ".global-notification--error",
        "#general-error",
    ],
}

# Dashboard selectors
DASHBOARD_SELECTORS = {
    "circuits_tab": [
        "a[href*='type=circuits']",
        "button:has-text('Circuits')",
        "[data-testid='circuits-tab']",
    ],
    "create_button": [
        "button:has-text('Create')",
        "[data-testid='create-button']",
        "button.create-button",
        "button:has-text('+ Create')",
    ],
    "create_circuit_item": [
        "a.button-circuits",
        ".dropdown-item:has-text('Circuits')",
        "a[class*='button-circuits']",
        "button:has-text('Circuit')",
        "a:has-text('Circuit')",
        "[data-testid='create-circuit']",
        "li:has-text('Circuit')",
    ],
    "circuit_cards": [
        "[data-testid='design-card']",
        ".design-card",
        ".gallery-item",
        "a[href*='/things/'][href*='/editel']",
        ".thing-card",
    ],
    "circuit_card_title": [
        "[data-testid='design-title']",
        ".design-title",
        ".card-title",
        "h3",
        "h4",
    ],
}

# Editor selectors
EDITOR_SELECTORS = {
    # Main container
    "editor_canvas": [
        "#breadboardTab",
        "#breadboardTab .hasSVG svg",
        ".root_container.js-editor--circuit",
        "#canvas-container",
        ".schematic-canvas",
        "svg.schematic",
        "#editor-content",
        ".editor-canvas",
        "canvas",
    ],
    # Header bar
    "circuit_title": [
        "#topnav-title-text",
        ".js-circuit-menu-title",
        "#topnav-title-input",
        ".js-circuit-menu-title-input",
        ".sitemenu__title__pill",
        "input#thing-title",
        "input[name='title']",
        "[data-testid='editor-title']",
        ".header-title input",
        "span.thing-title",
    ],
    "circuit_title_input": [
        "#topnav-title-input",
        ".js-circuit-menu-title-input",
        "input#topnav-title-input",
    ],
    "circuit_title_pill": [
        ".sitemenu__title__pill",
        "#topnav-title-container",
        "#topnav-title-text",
    ],
    "start_simulation_btn": [
        "a#SIMULATION_ID:has-text('Start Simulation')",
        "a#SIMULATION_ID",
        "a.js-toggleSimulation",
        "a[data-event='simulate']",
        "button:has-text('Start Simulation')",
        "[data-testid='start-simulation-btn']",
        ".btn-start-simulation",
        "button[title*='Start Simulation']",
    ],
    "stop_simulation_btn": [
        "a#SIMULATION_ID:has-text('Stop Simulation')",
        "a#SIMULATION_ID:has(.js-simulation-stop:not(.hide))",
        "a.js-toggleSimulation:has-text('Stop Simulation')",
        "button:has-text('Stop Simulation')",
        "[data-testid='stop-simulation-btn']",
        ".btn-stop-simulation",
        "button[title*='Stop Simulation']",
    ],
    "simulation_text": [
        ".js-simulation-text",
        "#SIMULATION_ID .circ_btn__txt",
    ],
    "simulation_timer": [
        ".simulation-time",
        "[data-testid='simulation-time']",
        ".sim-time-display",
    ],
    "code_toggle_btn": [
        "a#CODE_EDITOR_ID",
        "a.js-toggle_code_panel",
        "a[data-event='code-editor']",
        "a.circ_btn:has-text('Code')",
        "button:has-text('Code')",
        "[data-testid='code-editor-btn']",
        "#code-button",
        ".btn-code",
    ],
    "code_panel_active": [
        ".js-tpl-target__code_panel:not(.hide):not([style*='display: none']):not([style*='height: 0px'])",
        "a#CODE_EDITOR_ID.active",
        "a.js-toggle_code_panel.active",
        "a.circ_btn.active[data-event='code-editor']",
    ],
    "components_toggle_btn": [
        "button.workspace-switcher__button:has-text('Components')",
        "button:has-text('Components')",
        "[data-testid='components-drawer-btn']",
        ".btn-components",
    ],
    "rotate_btn": [
        "a#ROTATE_ID",
        "a.js-rotate",
        "button[title*='Rotate']",
        "button[aria-label*='Rotate']",
        ".btn-rotate",
        "[data-testid='rotate-btn']",
    ],
    "delete_btn": [
        "a#DELETE_ID",
        "a.js-delete",
        "button[title*='Delete']",
        "button[aria-label*='Delete']",
        ".btn-delete",
        "[data-testid='delete-btn']",
    ],
    "undo_btn": [
        "a#UNDO_ID",
        "a.js-undo",
    ],
    "redo_btn": [
        "a#REDO_ID",
        "a.js-redo",
    ],
    "copy_btn": [
        "a#COPY_ID",
        "a.js-copy",
    ],
    "paste_btn": [
        "a#PASTE_ID",
        "a.js-paste",
    ],
    "flip_btn": [
        "a#FLIP_ID",
        "a.js-flip",
    ],
    "zoom_fit_btn": [
        "a#ZOOM_FIT_ID",
        "a.js-zoom_fit",
        "a[data-event='zoom-fit']",
        "a[data-event='zoom_fit']",
        "button[title*='Fit']",
        "button[aria-label*='Fit']",
        ".btn-zoom-fit",
    ],
    "zoom_in_btn": [
        "a#ZOOM_IN_ID",
        "a.js-zoom_in",
        "a[data-event='zoom-in']",
        "button[title*='Zoom In']",
        "button[aria-label*='Zoom In']",
    ],
    "zoom_out_btn": [
        "a#ZOOM_OUT_ID",
        "a.js-zoom_out",
        "a[data-event='zoom-out']",
        "button[title*='Zoom Out']",
        "button[aria-label*='Zoom Out']",
    ],
    "workspace_switcher": [
        ".workspace-switcher__group",
        ".workspace-switcher",
    ],
    "workspace_circuits_btn": [
        "button.workspace-switcher__button:has-text('Circuits')",
        "button.workspace-switcher__button[communication='47']",
        ".workspace-switcher__button:has-text('Circuits')",
    ],
    "workspace_schematic_btn": [
        "button.workspace-switcher__button:has-text('Schematic')",
        "button.workspace-switcher__button[communication='48']",
        ".workspace-switcher__button:has-text('Schematic')",
    ],
    "workspace_components_btn": [
        "button.workspace-switcher__button:has-text('Components')",
        "button.workspace-switcher__button[communication='49']",
        ".workspace-switcher__button:has-text('Components')",
    ],
    "wire_color_dropdown": [
        "a.editor__dropdown__button[data-event='wire-color']",
        ".js-wire-color-container .editor__dropdown__button",
        "select.wire-color",
        "[data-testid='wire-color']",
        ".wire-color-picker",
    ],
    "wire_type_dropdown": [
        "a.editor__dropdown__button[data-event='wire-type']",
        ".js-wire-type-container .editor__dropdown__button",
        "select.wire-type",
        "[data-testid='wire-type']",
    ],
}

# Components drawer selectors
COMPONENTS_SELECTORS = {
    "drawer": [
        ".editor__component_picker__groups__items",
        ".editor__component_picker__groups",
        ".editor__component_picker",
        ".components-drawer",
        ".catalog-drawer",
        "[data-testid='components-panel']",
        "#component-sidebar",
    ],
    "items_container": [
        ".editor__component_picker__groups__items",
        ".editor__component_picker__groups",
    ],
    "search_input": [
        "input#q[data-event='component-search']",
        "form.js-component_search input#q",
        "input#q",
        ".editor__component_picker__groups__search input",
        "input[placeholder*='Search']",
        ".components-search input",
        "[data-testid='components-search']",
    ],
    "search_btn": [
        "button.js-search-btn",
        ".editor__component_picker__groups__search button[type='submit']",
    ],
    "search_clear_btn": [
        "a.js-search-clear__btn",
        "a[data-event='component-search-clear']",
    ],
    "category_select": [
        "a#COMPONENT_CATEGORY_SELECT",
        "a[data-event='component-group-select']",
        "select.components-category",
        "[data-testid='components-category']",
    ],
    "component_item": [
        ".editor__component_picker__groups__item",
        ".editor__component_picker__groups__item.grid__item",
        "div[data-did]",
        ".editor__component_picker .component",
        ".catalog-item",
        ".component-card",
        "[data-component-name]",
        "div[role='listitem']",
    ],
    "component_title": [
        ".editor__component_picker__groups__item__grid__title",
        ".editor__component_picker__groups__item__list__title",
    ],
    "blocking_overlays": [
        ".js-tpl-target__code_panel",
        ".modal:not(.hide)",
        ".ui-dialog:not(.hidden)",
        ".confirm-dialog",
    ],
    "modal_close": [
        ".modal .close",
        ".modal button.close",
        ".ui-dialog-titlebar-close",
        "button[aria-label='Close']",
        ".js-modal-close",
    ],
}

# Code panel selectors
CODE_SELECTORS = {
    "panel": [
        ".js-tpl-target__code_panel",
        "#scratchDiv",
        ".code_panel",
        ".code-panel",
        "#code-editor-drawer",
        ".code_editor",
        ".code-editor",
        ".injectionDiv",
        ".blocklySvg",
        ".blocklyRelativeWrapper",
        "[data-testid='code-panel']",
    ],
    "mode_select": [
        "a.editor__dropdown__button:has-text('Text')",
        "a.editor__dropdown__button:has-text('Blocks')",
        ".code_panel .editor__dropdown__button",
        "select#code-mode",
        "select.code-mode-select",
        ".code-mode-select select",
        ".code_editor__mode_select select",
        "[data-testid='code-mode-select']",
    ],
    "confirm_modal_continue": [
        ".modal button:has-text('Continue')",
        "button:has-text('Continue')",
        "button:has-text('OK')",
        ".confirm-dialog button.btn-primary",
        ".modal-footer button.btn-primary",
    ],
    "code_textarea": [
        "textarea.js-code_editor__textarea",
        "textarea.code_editor__textarea",
        ".js-code_editor__textarea",
        ".code_editor__textarea",
        "textarea.code-editor",
        "textarea[name='code']",
    ],
    "ace_editor": [
        ".ace_editor",
        ".ace_text-input",
        "textarea.ace_text-input",
    ],
    "codemirror_editor": [
        ".CodeMirror",
        ".cm-content",
    ],
    "codemirror_input": [
        ".CodeMirror textarea",
        ".CodeMirror [contenteditable='true']",
        ".cm-content",
    ],
    "hidden_code_textarea": [
        "textarea.js-code_editor__textarea",
        "textarea.code_editor__textarea",
        ".js-code_editor__textarea",
    ],
    "save_status": [
        ".status-saved",
        "[data-testid='save-status']",
        ".autosave-indicator",
        ".save-indicator",
        ".header__saving-status",
    ],
}

# Serial monitor selectors
SERIAL_SELECTORS = {
    "toggle_btn": [
        "a#SERIAL_MONITOR_ID",
        "a.js-toggle_serial_monitor",
        "a[data-event='serial-monitor']",
        "button:has-text('Serial Monitor')",
        ".serial-monitor-toggle",
        "[data-testid='serial-monitor-toggle']",
    ],
    "panel": [
        ".code_panel__serial",
        ".js-code_panel__serial",
        ".serial-monitor",
        "[data-testid='serial-monitor-panel']",
        "#serial-monitor-drawer",
    ],
    "output_log": [
        ".js-code_editor__serial-monitor__content",
        ".js-code_panel__serial__text",
        ".code_panel__serial__content__text",
        ".serial-output",
        "textarea.serial-log",
        "[data-testid='serial-output']",
        ".serial-messages",
        ".monitor-content",
    ],
    "input_field": [
        "input.js-code_panel__serial__input",
        "input.code_panel__serial__input",
        ".code_panel__serial__bottom input",
        ".code_panel__serial input",
        "input.serial-input",
        "[data-testid='serial-input']",
        ".serial-entry input",
    ],
    "send_btn": [
        "a.js-code_panel__serial__send",
        "a[data-event='serial-send']",
        ".code_panel__serial__button.js-code_panel__serial__send",
        ".code_panel__serial a:has-text('Send')",
        ".code_panel__serial button:has-text('Send')",
        "button:has-text('Send')",
        "[data-testid='serial-send-btn']",
        ".btn-serial-send",
    ],
    "clear_btn": [
        "a.js-code_panel__serial__clear",
        "a[data-event='serial-clear']",
        ".code_panel__serial__button.js-code_panel__serial__clear",
        ".code_panel__serial a:has-text('Clear')",
        ".code_panel__serial button:has-text('Clear')",
        "button:has-text('Clear')",
        "[data-testid='serial-clear-btn']",
        ".btn-serial-clear",
    ],
    "graph_btn": [
        "a.js-code_panel__serial__toggle_graph",
        "a[data-event='serial-graph']",
    ],
    "baud_rate_select": [
        ".code_panel__serial select",
        "select.serial-baud",
        "[data-testid='serial-baud']",
    ],
}

