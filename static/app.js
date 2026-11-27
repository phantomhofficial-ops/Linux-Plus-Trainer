(() => {
  "use strict";

  const THEME_KEY = "linux_plus_theme";
  const MODE_KEY = "linux_plus_mode";
  const DIFFICULTY_KEY = "linux_plus_difficulty";
  const QUIZ_LENGTH_KEY = "linux_plus_quiz_length";
  const HUB_TAB_KEY = "linux_plus_hub_tab";
  const BACKEND_KEY = "linux_plus_sandbox_backend";
  const CUSTOM_UI_KEY = "linux_plus_custom_ui";
  const CUSTOM_SLOTS_KEY = "linux_plus_custom_slots";

  const VALID_THEMES = new Set([
    "osrs",
    "cyberpunk",
    "oot",
    "halo",
    "nordic",
    "matrix",
    "custom1",
    "custom2",
  ]);
  const THEME_PALETTES = {
    osrs: { bg: "#18130e", panel: "#3e3529", accent: "#ff981f", text: "#ece2d0", radius: 3 },
    cyberpunk: { bg: "#060811", panel: "#0c111e", accent: "#00f0ff", text: "#e6f7ff", radius: 2 },
    oot: { bg: "#07121c", panel: "#0e1f38", accent: "#f5c842", text: "#f7f1de", radius: 6 },
    halo: { bg: "#07111e", panel: "#0d1e34", accent: "#38bdf8", text: "#e6f4ff", radius: 4 },
    nordic: { bg: "#242933", panel: "#2e3440", accent: "#88c0d0", text: "#eceff4", radius: 8 },
    matrix: { bg: "#030904", panel: "#071309", accent: "#22c55e", text: "#d1fae5", radius: 4 },
    custom1: { bg: "#0f1020", panel: "#191b30", accent: "#818cf8", text: "#eef2ff", radius: 6 },
    custom2: { bg: "#181412", panel: "#27201c", accent: "#f59e0b", text: "#fef3c7", radius: 6 },
  };
  const UI_FONT_MAP = {
    "modern-sans": '"Space Grotesk", "Inter", system-ui, sans-serif',
    humanist: '"Plus Jakarta Sans", "Noto Sans", "Segoe UI", sans-serif',
    scifi: '"Orbitron", "Eurostile", "Rajdhani", sans-serif',
    "rpg-serif": '"Cinzel", "Palatino Linotype", Georgia, serif',
    editorial: '"Merriweather", Georgia, "Liberation Serif", serif',
    arcade: '"VT323", "Silkscreen", "Courier New", monospace',
    legible: '"Atkinson Hyperlegible", Verdana, Tahoma, sans-serif',
    rounded: '"Nunito", ui-rounded, "Trebuchet MS", sans-serif',
    "tech-mono": '"JetBrains Mono", "Fira Code", monospace',
  };
  const MONO_FONT_MAP = {
    jetbrains: '"JetBrains Mono", "Noto Sans Mono", monospace',
    fira: '"Fira Code", "DejaVu Sans Mono", monospace',
    "source-code": '"Source Code Pro", Menlo, monospace',
    "ibm-plex": '"IBM Plex Mono", "Liberation Mono", monospace',
    hack: 'Hack, "DejaVu Sans Mono", monospace',
    courier: '"Courier New", Courier, monospace',
    "retro-crt": '"VT323", "Share Tech Mono", monospace',
  };

  function defaultCustomUi() {
    return {
      colors: { bg: null, panel: null, accent: null, text: null },
      uiFont: "default",
      monoFont: "default",
      fontScale: 100,
      radius: null,
      effects: true,
      density: "comfortable",
    };
  }

  const state = {
    theme: "cyberpunk",
    customUi: defaultCustomUi(),
    customSlots: {},
    activeColorTarget: "accent",
    colorEditorMode: "hsb",
    mode: "multiple_choice",
    difficulty: "all",
    quizLength: "all",
    hubTab: "practice",
    customCategories: [],
    customDomains: [],
    sandboxBackend: "auto",
    sandboxCapabilities: null,
    dashboard: null,
    labs: [],
    examsMeta: null,
    activeSession: null,
    activeExam: null,
    examTimerInterval: null,
    lastScorecard: null,
    reviewFilter: "all",
    activeLabSession: null,
    labCmdHistory: [],
    labHistoryIdx: -1,
    lastStartParams: null,
    pendingResetCategory: null,
    awaitingNext: false,
    busy: false,
  };

  const els = {
    alert: document.getElementById("global-alert"),
    hudLevel: document.getElementById("hud-level"),
    hudXp: document.getElementById("hud-xp"),
    hudAccuracy: document.getElementById("hud-accuracy"),
    themeBtns: Array.from(document.querySelectorAll("[data-theme-target]")),
    btnThemeOsrs: document.getElementById("btn-theme-osrs"),
    btnThemeCyberpunk: document.getElementById("btn-theme-cyberpunk"),
    btnThemeOot: document.getElementById("btn-theme-oot"),
    btnOpenCustomizer: document.getElementById("btn-open-customizer"),
    btnCloseCustomizer: document.getElementById("btn-close-customizer"),
    customizerBackdrop: document.getElementById("customizer-backdrop"),
    customizerDrawer: document.getElementById("customizer-drawer"),
    presetBtns: Array.from(document.querySelectorAll("[data-theme-preset]")),
    btnSaveCustom1: document.getElementById("btn-save-custom1"),
    btnSaveCustom2: document.getElementById("btn-save-custom2"),
    customSlotStatus: document.getElementById("custom-slot-status"),
    colorTargetBtns: Array.from(document.querySelectorAll("[data-color-target]")),
    swatchBg: document.getElementById("swatch-bg"),
    hexBg: document.getElementById("hex-bg"),
    swatchPanel: document.getElementById("swatch-panel"),
    hexPanel: document.getElementById("hex-panel"),
    swatchAccent: document.getElementById("swatch-accent"),
    hexAccent: document.getElementById("hex-accent"),
    swatchText: document.getElementById("swatch-text"),
    hexText: document.getElementById("hex-text"),
    editorColorSwatch: document.getElementById("editor-color-swatch"),
    editorHexInput: document.getElementById("editor-hex-input"),
    colorModeBtns: Array.from(document.querySelectorAll("[data-color-mode]")),
    colorSlidersHsb: document.getElementById("color-sliders-hsb"),
    colorSlidersRgb: document.getElementById("color-sliders-rgb"),
    sliderH: document.getElementById("slider-h"),
    valH: document.getElementById("val-h"),
    sliderS: document.getElementById("slider-s"),
    valS: document.getElementById("val-s"),
    sliderB: document.getElementById("slider-b"),
    valB: document.getElementById("val-b"),
    sliderR: document.getElementById("slider-r"),
    valR: document.getElementById("val-r"),
    sliderG: document.getElementById("slider-g"),
    valG: document.getElementById("val-g"),
    sliderBRgb: document.getElementById("slider-b-rgb"),
    valBRgb: document.getElementById("val-b-rgb"),
    customUiFont: document.getElementById("custom-ui-font"),
    customMonoFont: document.getElementById("custom-mono-font"),
    customFontScale: document.getElementById("custom-font-scale"),
    customFontScaleVal: document.getElementById("custom-font-scale-val"),
    customRadius: document.getElementById("custom-radius"),
    customRadiusVal: document.getElementById("custom-radius-val"),
    customEffectsToggle: document.getElementById("custom-effects-toggle"),
    densityBtns: Array.from(document.querySelectorAll("[data-density-target]")),
    btnRandomizeCustomizer: document.getElementById("btn-randomize-customizer"),
    btnResetCustomizer: document.getElementById("btn-reset-customizer"),

    dashboardView: document.getElementById("dashboard-view"),
    quizView: document.getElementById("quiz-view"),
    labView: document.getElementById("lab-view"),
    summaryView: document.getElementById("summary-view"),
    examView: document.getElementById("exam-view"),
    examScorecardView: document.getElementById("exam-scorecard-view"),

    hubTabBtns: Array.from(document.querySelectorAll("[data-hub-tab]")),
    hubPanelPractice: document.getElementById("hub-panel-practice"),
    hubPanelExams: document.getElementById("hub-panel-exams"),
    hubPanelLabs: document.getElementById("hub-panel-labs"),
    tabLabsCount: document.getElementById("tab-labs-count"),
    lengthBtns: Array.from(document.querySelectorAll("[data-length]")),

    btnToggleCustomMix: document.getElementById("btn-toggle-custom-mix"),
    customMixBody: document.getElementById("custom-mix-body"),
    customMixCategories: document.getElementById("custom-mix-categories"),
    customMixDomains: document.getElementById("custom-mix-domains"),
    customMixSummary: document.getElementById("custom-mix-summary"),
    btnClearCustomMix: document.getElementById("btn-clear-custom-mix"),
    btnStartCustomMix: document.getElementById("btn-start-custom-mix"),

    examAttemptsCount: document.getElementById("exam-attempts-count"),
    examWeightsBar: document.getElementById("exam-weights-bar"),
    examPresetsGrid: document.getElementById("exam-presets-grid"),
    examHistoryList: document.getElementById("exam-history-list"),

    btnExamExit: document.getElementById("btn-exam-exit"),
    examTitleBadge: document.getElementById("exam-title-badge"),
    examDomainBadge: document.getElementById("exam-domain-badge"),
    examDifficultyBadge: document.getElementById("exam-difficulty-badge"),
    examCounter: document.getElementById("exam-counter"),
    examTimerDisplay: document.getElementById("exam-timer-display"),
    btnExamSubmitOpen: document.getElementById("btn-exam-submit-open"),
    examQNum: document.getElementById("exam-q-num"),
    btnExamFlag: document.getElementById("btn-exam-flag"),
    examQuestionPrompt: document.getElementById("exam-question-prompt"),
    examMcOptions: document.getElementById("exam-mc-options"),
    btnExamPrev: document.getElementById("btn-exam-prev"),
    btnExamNext: document.getElementById("btn-exam-next"),
    examNavCounts: document.getElementById("exam-nav-counts"),
    examNavigatorGrid: document.getElementById("exam-navigator-grid"),

    examSubmitModal: document.getElementById("exam-submit-modal"),
    examSubmitModalBody: document.getElementById("exam-submit-modal-body"),
    btnCancelExamSubmit: document.getElementById("btn-cancel-exam-submit"),
    btnConfirmExamSubmit: document.getElementById("btn-confirm-exam-submit"),

    scorecardSubtitle: document.getElementById("scorecard-subtitle"),
    scorecardTitle: document.getElementById("scorecard-title"),
    scorecardPassBadge: document.getElementById("scorecard-pass-badge"),
    scorecardScaled: document.getElementById("scorecard-scaled"),
    scorecardCorrect: document.getElementById("scorecard-correct"),
    scorecardAccuracy: document.getElementById("scorecard-accuracy"),
    scorecardAnswered: document.getElementById("scorecard-answered"),
    scorecardTime: document.getElementById("scorecard-time"),
    scorecardDomainBars: document.getElementById("scorecard-domain-bars"),
    btnScorecardRetake: document.getElementById("btn-scorecard-retake"),
    btnScorecardDashboard: document.getElementById("btn-scorecard-dashboard"),
    reviewFilterBtns: Array.from(document.querySelectorAll("[data-review-filter]")),
    scorecardReviewList: document.getElementById("scorecard-review-list"),

    labsCompletedCount: document.getElementById("labs-completed-count"),
    labsTotalCount: document.getElementById("labs-total-count"),
    labsGrid: document.getElementById("labs-grid"),
    dashboardBackendBadge: document.getElementById("dashboard-backend-badge"),
    dashboardBackendToggle: document.getElementById("dashboard-backend-toggle"),
    labBackendBadge: document.getElementById("lab-backend-badge"),
    labBackendToggle: document.getElementById("lab-backend-toggle"),

    btnLabBack: document.getElementById("btn-lab-back"),
    labTitleBadge: document.getElementById("lab-title-badge"),
    labDomainBadge: document.getElementById("lab-domain-badge"),
    labDifficultyBadge: document.getElementById("lab-difficulty-badge"),
    labStatusBadge: document.getElementById("lab-status-badge"),
    labObjectiveText: document.getElementById("lab-objective-text"),
    labChecklist: document.getElementById("lab-checklist"),
    labPassBanner: document.getElementById("lab-pass-banner"),
    labHintBox: document.getElementById("lab-hint-box"),
    labHintText: document.getElementById("lab-hint-text"),
    labSolutionBox: document.getElementById("lab-solution-box"),
    labSolutionCode: document.getElementById("lab-solution-code"),
    btnLabCheck: document.getElementById("btn-lab-check"),
    btnLabHint: document.getElementById("btn-lab-hint"),
    btnLabReset: document.getElementById("btn-lab-reset"),
    btnLabSolution: document.getElementById("btn-lab-solution"),
    labCwdBadge: document.getElementById("lab-cwd-badge"),
    labTerminalOutput: document.getElementById("lab-terminal-output"),
    labCmdForm: document.getElementById("lab-cmd-form"),
    labTerminalPrompt: document.getElementById("lab-terminal-prompt"),
    labCmdInput: document.getElementById("lab-cmd-input"),
    btnLabRun: document.getElementById("btn-lab-run"),

    modeMcBtn: document.getElementById("mode-mc-btn"),
    modeExactBtn: document.getElementById("mode-exact-btn"),
    diffBtns: Array.from(document.querySelectorAll(".diff-btn")),
    diffCountAll: document.getElementById("diff-count-all"),
    diffCountBeginner: document.getElementById("diff-count-beginner"),
    diffCountIntermediate: document.getElementById("diff-count-intermediate"),
    diffCountHard: document.getElementById("diff-count-hard"),
    btnStartAll: document.getElementById("btn-start-all"),
    btnStartMissed: document.getElementById("btn-start-missed"),
    btnOpenReset: document.getElementById("btn-open-reset"),
    allCount: document.getElementById("all-count"),
    missedCount: document.getElementById("missed-count"),
    overallAnswered: document.getElementById("overall-answered"),
    overallCorrect: document.getElementById("overall-correct"),
    categoriesGrid: document.getElementById("categories-grid"),

    btnBackDashboard: document.getElementById("btn-back-dashboard"),
    quizScopeBadge: document.getElementById("quiz-scope-badge"),
    quizDomainBadge: document.getElementById("quiz-domain-badge"),
    quizDifficultyBadge: document.getElementById("quiz-difficulty-badge"),
    quizCounter: document.getElementById("quiz-counter"),
    sessionXp: document.getElementById("session-xp"),
    quizProgressFill: document.getElementById("quiz-progress-fill"),
    questionPrompt: document.getElementById("question-prompt"),

    mcContainer: document.getElementById("mc-container"),
    mcOptions: document.getElementById("mc-options"),
    btnMcHint: document.getElementById("btn-mc-hint"),
    btnMcSkip: document.getElementById("btn-mc-skip"),

    exactContainer: document.getElementById("exact-container"),
    exactForm: document.getElementById("exact-form"),
    cmdInput: document.getElementById("cmd-input"),
    btnExactSubmit: document.getElementById("btn-exact-submit"),
    btnExactHint: document.getElementById("btn-exact-hint"),
    btnExactSkip: document.getElementById("btn-exact-skip"),

    hintBox: document.getElementById("hint-box"),
    hintText: document.getElementById("hint-text"),

    feedbackPanel: document.getElementById("feedback-panel"),
    feedbackHitsplat: document.getElementById("feedback-hitsplat"),
    feedbackStatusLabel: document.getElementById("feedback-status-label"),
    feedbackXpLabel: document.getElementById("feedback-xp-label"),
    feedbackUserAnswerRow: document.getElementById("feedback-user-answer-row"),
    feedbackUserAnswer: document.getElementById("feedback-user-answer"),
    feedbackCorrectChoice: document.getElementById("feedback-correct-choice"),
    feedbackVariantsRow: document.getElementById("feedback-variants-row"),
    feedbackVariants: document.getElementById("feedback-variants"),
    feedbackDomain: document.getElementById("feedback-domain"),
    feedbackExplanation: document.getElementById("feedback-explanation"),
    btnNextQuestion: document.getElementById("btn-next-question"),

    summaryScopeText: document.getElementById("summary-scope-text"),
    sumCorrect: document.getElementById("sum-correct"),
    sumAccuracy: document.getElementById("sum-accuracy"),
    sumXp: document.getElementById("sum-xp"),
    sumMeta: document.getElementById("sum-meta"),
    btnTrainAgain: document.getElementById("btn-train-again"),
    btnSummaryMissed: document.getElementById("btn-summary-missed"),
    btnSummaryDashboard: document.getElementById("btn-summary-dashboard"),

    resetModal: document.getElementById("reset-modal"),
    resetModalTitle: document.getElementById("reset-modal-title"),
    resetModalBody: document.getElementById("reset-modal-body"),
    btnCancelReset: document.getElementById("btn-cancel-reset"),
    btnConfirmReset: document.getElementById("btn-confirm-reset"),
  };

  function showAlert(message) {
    if (!message) {
      els.alert.classList.add("hidden");
      els.alert.textContent = "";
      return;
    }
    els.alert.textContent = message;
    els.alert.classList.remove("hidden");
  }

  function normalizeHex(raw) {
    if (typeof raw !== "string") return null;
    const cleaned = raw.trim().replace(/^#/, "");
    if (/^[0-9a-fA-F]{6}$/.test(cleaned)) {
      return `#${cleaned.toLowerCase()}`;
    }
    return null;
  }

  function hexToRgb(hex) {
    const norm = normalizeHex(hex) || "#000000";
    const intVal = parseInt(norm.slice(1), 16);
    return {
      r: (intVal >> 16) & 255,
      g: (intVal >> 8) & 255,
      b: intVal & 255,
    };
  }

  function rgbToHex(r, g, b) {
    const clamp = (n) => Math.max(0, Math.min(255, Math.round(n)));
    return (
      "#" +
      [clamp(r), clamp(g), clamp(b)]
        .map((n) => n.toString(16).padStart(2, "0"))
        .join("")
    );
  }

  function rgbToHsb(r, g, b) {
    const rn = r / 255;
    const gn = g / 255;
    const bn = b / 255;
    const max = Math.max(rn, gn, bn);
    const min = Math.min(rn, gn, bn);
    const d = max - min;
    let h = 0;
    if (d !== 0) {
      if (max === rn) h = ((gn - bn) / d) % 6;
      else if (max === gn) h = (bn - rn) / d + 2;
      else h = (rn - gn) / d + 4;
      h = Math.round(h * 60);
      if (h < 0) h += 360;
    }
    const s = max === 0 ? 0 : Math.round((d / max) * 100);
    const v = Math.round(max * 100);
    return { h, s, b: v };
  }

  function hsbToRgb(h, s, b) {
    const hn = ((h % 360) + 360) % 360;
    const sn = Math.max(0, Math.min(100, s)) / 100;
    const vn = Math.max(0, Math.min(100, b)) / 100;
    const c = vn * sn;
    const x = c * (1 - Math.abs(((hn / 60) % 2) - 1));
    const m = vn - c;
    let r1 = 0, g1 = 0, b1 = 0;
    if (hn < 60) [r1, g1, b1] = [c, x, 0];
    else if (hn < 120) [r1, g1, b1] = [x, c, 0];
    else if (hn < 180) [r1, g1, b1] = [0, c, x];
    else if (hn < 240) [r1, g1, b1] = [0, x, c];
    else if (hn < 300) [r1, g1, b1] = [x, 0, c];
    else [r1, g1, b1] = [c, 0, x];
    return {
      r: Math.round((r1 + m) * 255),
      g: Math.round((g1 + m) * 255),
      b: Math.round((b1 + m) * 255),
    };
  }

  function getResolvedColors() {
    const palette = THEME_PALETTES[state.theme] || THEME_PALETTES.cyberpunk;
    const c = state.customUi.colors || {};
    return {
      bg: c.bg || palette.bg,
      panel: c.panel || palette.panel,
      accent: c.accent || palette.accent,
      text: c.text || palette.text,
    };
  }

  function syncColorEditor() {
    const resolved = getResolvedColors();
    if (els.swatchBg) els.swatchBg.style.backgroundColor = resolved.bg;
    if (els.hexBg) els.hexBg.textContent = resolved.bg;
    if (els.swatchPanel) els.swatchPanel.style.backgroundColor = resolved.panel;
    if (els.hexPanel) els.hexPanel.textContent = resolved.panel;
    if (els.swatchAccent) els.swatchAccent.style.backgroundColor = resolved.accent;
    if (els.hexAccent) els.hexAccent.textContent = resolved.accent;
    if (els.swatchText) els.swatchText.style.backgroundColor = resolved.text;
    if (els.hexText) els.hexText.textContent = resolved.text;

    els.colorTargetBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.colorTarget === state.activeColorTarget);
    });

    const activeHex = resolved[state.activeColorTarget] || resolved.accent;
    if (els.editorColorSwatch) els.editorColorSwatch.style.backgroundColor = activeHex;
    if (els.editorHexInput && document.activeElement !== els.editorHexInput) {
      els.editorHexInput.value = activeHex;
    }

    const rgb = hexToRgb(activeHex);
    const hsb = rgbToHsb(rgb.r, rgb.g, rgb.b);
    if (els.sliderH) els.sliderH.value = String(hsb.h);
    if (els.valH) els.valH.textContent = `${hsb.h}°`;
    if (els.sliderS) els.sliderS.value = String(hsb.s);
    if (els.valS) els.valS.textContent = `${hsb.s}%`;
    if (els.sliderB) els.sliderB.value = String(hsb.b);
    if (els.valB) els.valB.textContent = `${hsb.b}%`;

    if (els.sliderR) els.sliderR.value = String(rgb.r);
    if (els.valR) els.valR.textContent = String(rgb.r);
    if (els.sliderG) els.sliderG.value = String(rgb.g);
    if (els.valG) els.valG.textContent = String(rgb.g);
    if (els.sliderBRgb) els.sliderBRgb.value = String(rgb.b);
    if (els.valBRgb) els.valBRgb.textContent = String(rgb.b);

    const isRgb = state.colorEditorMode === "rgb";
    if (els.colorSlidersHsb) els.colorSlidersHsb.classList.toggle("hidden", isRgb);
    if (els.colorSlidersRgb) els.colorSlidersRgb.classList.toggle("hidden", !isRgb);
    els.colorModeBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.colorMode === state.colorEditorMode);
    });
  }

  function setActiveTargetColor(hex) {
    const norm = normalizeHex(hex);
    if (!norm) return;
    applyCustomUi({
      ...state.customUi,
      colors: { ...state.customUi.colors, [state.activeColorTarget]: norm },
    });
  }

  function syncCustomizerInputs() {
    const palette = THEME_PALETTES[state.theme] || THEME_PALETTES.cyberpunk;
    syncColorEditor();

    if (els.customUiFont) els.customUiFont.value = state.customUi.uiFont || "default";
    if (els.customMonoFont) els.customMonoFont.value = state.customUi.monoFont || "default";

    const scale = state.customUi.fontScale || 100;
    if (els.customFontScale) els.customFontScale.value = String(scale);
    if (els.customFontScaleVal) els.customFontScaleVal.textContent = `${scale}%`;

    const hasRadius = typeof state.customUi.radius === "number";
    const radiusNum = hasRadius ? state.customUi.radius : palette.radius;
    if (els.customRadius) els.customRadius.value = String(radiusNum);
    if (els.customRadiusVal) {
      els.customRadiusVal.textContent = hasRadius ? `${radiusNum}px` : `Default (${palette.radius}px)`;
    }

    if (els.customEffectsToggle) {
      els.customEffectsToggle.checked = state.customUi.effects !== false;
    }

    const density = state.customUi.density === "compact" ? "compact" : "comfortable";
    els.densityBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.densityTarget === density);
    });
  }

  function applyCustomUi(nextSettings, { save = true } = {}) {
    const merged = {
      ...defaultCustomUi(),
      ...nextSettings,
      colors: {
        ...defaultCustomUi().colors,
        ...(nextSettings && nextSettings.colors ? nextSettings.colors : {}),
      },
    };
    state.customUi = merged;
    const root = document.documentElement;

    // Color overrides
    if (merged.colors.bg) {
      root.style.setProperty("--bg-page", merged.colors.bg);
      root.style.setProperty("--bg-page-accent", merged.colors.bg);
    } else {
      root.style.removeProperty("--bg-page");
      root.style.removeProperty("--bg-page-accent");
    }

    if (merged.colors.panel) {
      root.style.setProperty("--bg-panel", merged.colors.panel);
      root.style.setProperty("--bg-panel-alt", merged.colors.panel);
      root.style.setProperty("--bg-card", merged.colors.panel);
    } else {
      root.style.removeProperty("--bg-panel");
      root.style.removeProperty("--bg-panel-alt");
      root.style.removeProperty("--bg-card");
    }

    if (merged.colors.accent) {
      root.style.setProperty("--accent-primary", merged.colors.accent);
      root.style.setProperty("--border-light", merged.colors.accent);
      root.style.setProperty("--border-accent", merged.colors.accent);
      root.style.setProperty("--text-heading", merged.colors.accent);
    } else {
      root.style.removeProperty("--accent-primary");
      root.style.removeProperty("--border-light");
      root.style.removeProperty("--border-accent");
      root.style.removeProperty("--text-heading");
    }

    if (merged.colors.text) {
      root.style.setProperty("--text-primary", merged.colors.text);
    } else {
      root.style.removeProperty("--text-primary");
    }

    // Typography
    if (merged.uiFont && UI_FONT_MAP[merged.uiFont]) {
      root.style.setProperty("--font-ui", UI_FONT_MAP[merged.uiFont]);
      root.dataset.customFont = "true";
    } else {
      root.style.removeProperty("--font-ui");
      delete root.dataset.customFont;
    }

    if (merged.monoFont && MONO_FONT_MAP[merged.monoFont]) {
      root.style.setProperty("--font-mono", MONO_FONT_MAP[merged.monoFont]);
    } else {
      root.style.removeProperty("--font-mono");
    }

    // Font scale
    const scale = Math.min(125, Math.max(85, Number(merged.fontScale) || 100));
    merged.fontScale = scale;
    if (scale !== 100) {
      root.style.setProperty("--font-scale", String(scale / 100));
    } else {
      root.style.removeProperty("--font-scale");
    }

    // Corner radius
    if (typeof merged.radius === "number" && merged.radius >= 0 && merged.radius <= 16) {
      root.style.setProperty("--radius-panel", `${merged.radius}px`);
      root.dataset.customRadius = "true";
    } else {
      root.style.removeProperty("--radius-panel");
      delete root.dataset.customRadius;
    }

    // Effects & Density
    if (merged.effects === false) {
      root.dataset.effects = "off";
    } else {
      delete root.dataset.effects;
    }

    if (merged.density === "compact") {
      root.dataset.density = "compact";
    } else {
      delete root.dataset.density;
    }

    if (save) {
      try {
        localStorage.setItem(CUSTOM_UI_KEY, JSON.stringify(merged));
      } catch (e) {}
    }

    syncCustomizerInputs();
  }

  function applyTheme(theme, { clearColorOverrides = false } = {}) {
    const valid = VALID_THEMES.has(theme) ? theme : "cyberpunk";
    state.theme = valid;
    document.documentElement.dataset.theme = valid;
    try {
      localStorage.setItem(THEME_KEY, valid);
    } catch (e) {}
    els.themeBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.themeTarget === valid);
    });
    els.presetBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.themePreset === valid);
    });

    if ((valid === "custom1" || valid === "custom2") && state.customSlots[valid]) {
      applyCustomUi(state.customSlots[valid], { save: true });
      return;
    }

    if (clearColorOverrides) {
      applyCustomUi({
        ...state.customUi,
        colors: { bg: null, panel: null, accent: null, text: null },
        radius: null,
      });
    } else {
      syncCustomizerInputs();
    }
  }

  function saveCurrentLookToSlot(slotName) {
    if (slotName !== "custom1" && slotName !== "custom2") return;
    const resolved = getResolvedColors();
    const snapshot = {
      ...defaultCustomUi(),
      ...state.customUi,
      colors: { ...resolved },
    };
    state.customSlots[slotName] = snapshot;
    try {
      localStorage.setItem(CUSTOM_SLOTS_KEY, JSON.stringify(state.customSlots));
    } catch (e) {}
    applyTheme(slotName);
    if (els.customSlotStatus) {
      const label = slotName === "custom1" ? "Custom 1" : "Custom 2";
      els.customSlotStatus.textContent = `Saved current look to ${label}.`;
    }
  }

  function openCustomizer(show) {
    if (!els.customizerDrawer || !els.customizerBackdrop) return;
    if (show) {
      els.customizerBackdrop.classList.remove("hidden");
      els.customizerDrawer.classList.remove("hidden");
      requestAnimationFrame(() => {
        els.customizerDrawer.classList.add("open");
      });
      if (els.btnOpenCustomizer) els.btnOpenCustomizer.setAttribute("aria-expanded", "true");
    } else {
      els.customizerDrawer.classList.remove("open");
      els.customizerDrawer.classList.add("hidden");
      els.customizerBackdrop.classList.add("hidden");
      if (els.btnOpenCustomizer) els.btnOpenCustomizer.setAttribute("aria-expanded", "false");
    }
  }

  function resetCustomizerToThemeDefaults() {
    try {
      localStorage.removeItem(CUSTOM_UI_KEY);
    } catch (e) {}
    applyCustomUi(defaultCustomUi(), { save: false });
  }

  function randomizeAppearance() {
    const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
    const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
    const hsbHex = (h, s, b) => {
      const rgb = hsbToRgb(h, s, b);
      return rgbToHex(rgb.r, rgb.g, rgb.b);
    };

    const baseHue = randInt(0, 359);
    const harmonyOffsets = [180, 35, -35, 150, 210];
    const accentHue = (baseHue + pick(harmonyOffsets) + 360) % 360;

    const bgBrightness = randInt(5, 13);
    const panelBrightness = Math.min(19, Math.max(11, bgBrightness + randInt(5, 8)));

    const colors = {
      bg: hsbHex(baseHue, randInt(18, 42), bgBrightness),
      panel: hsbHex((baseHue + randInt(-10, 10) + 360) % 360, randInt(16, 38), panelBrightness),
      accent: hsbHex(accentHue, randInt(55, 95), randInt(68, 95)),
      text: hsbHex(accentHue, randInt(5, 20), randInt(88, 97)),
    };

    const uiKeys = ["default", ...Object.keys(UI_FONT_MAP)];
    const monoKeys = ["default", ...Object.keys(MONO_FONT_MAP)];

    applyCustomUi({
      ...state.customUi,
      colors,
      uiFont: pick(uiKeys),
      monoFont: pick(monoKeys),
      radius: randInt(0, 16),
    });

    if (els.customSlotStatus) {
      els.customSlotStatus.textContent = "Randomized! Click Custom 1 or Custom 2 to save.";
    }
  }

  function applyMode(mode) {
    const valid = mode === "exact_command" ? "exact_command" : "multiple_choice";
    state.mode = valid;
    try {
      localStorage.setItem(MODE_KEY, valid);
    } catch (e) {}
    els.modeMcBtn.classList.toggle("active", valid === "multiple_choice");
    els.modeExactBtn.classList.toggle("active", valid === "exact_command");
  }

  function applyDifficulty(difficulty) {
    const allowed = new Set(["all", "beginner", "intermediate", "hard"]);
    const valid = allowed.has(difficulty) ? difficulty : "all";
    state.difficulty = valid;
    try {
      localStorage.setItem(DIFFICULTY_KEY, valid);
    } catch (e) {}
    els.diffBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.difficulty === valid);
    });
    if (state.dashboard) {
      renderDashboard(state.dashboard);
    }
  }

  function switchHubTab(tabName) {
    const allowed = new Set(["practice", "exams", "labs"]);
    const valid = allowed.has(tabName) ? tabName : "practice";
    state.hubTab = valid;
    try {
      localStorage.setItem(HUB_TAB_KEY, valid);
    } catch (e) {}
    if (els.hubTabBtns) {
      els.hubTabBtns.forEach((btn) => {
        const active = btn.dataset.hubTab === valid;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
    }
    if (els.hubPanelPractice) els.hubPanelPractice.classList.toggle("hidden", valid !== "practice");
    if (els.hubPanelExams) els.hubPanelExams.classList.toggle("hidden", valid !== "exams");
    if (els.hubPanelLabs) els.hubPanelLabs.classList.toggle("hidden", valid !== "labs");
  }

  function applyQuizLength(lengthId) {
    const allowed = new Set(["short", "medium", "long", "all"]);
    const valid = allowed.has(lengthId) ? lengthId : "all";
    state.quizLength = valid;
    try {
      localStorage.setItem(QUIZ_LENGTH_KEY, valid);
    } catch (e) {}
    if (els.lengthBtns) {
      els.lengthBtns.forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.length === valid);
      });
    }
  }

  function switchView(viewName) {
    els.dashboardView.classList.toggle("hidden", viewName !== "dashboard");
    els.quizView.classList.toggle("hidden", viewName !== "quiz");
    els.labView.classList.toggle("hidden", viewName !== "lab");
    els.summaryView.classList.toggle("hidden", viewName !== "summary");
    if (els.examView) els.examView.classList.toggle("hidden", viewName !== "exam");
    if (els.examScorecardView) {
      els.examScorecardView.classList.toggle("hidden", viewName !== "exam-scorecard");
    }
  }

  async function apiJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Request failed");
    }
    return payload;
  }

  function renderDashboard(data) {
    state.dashboard = data;
    const overall = data.overall;
    const diff = state.difficulty || "all";
    const diffCounts = data.difficulty_counts || {};
    const missedByDiff = data.missed_by_difficulty || {};

    els.hudLevel.textContent = String(overall.total_level);
    els.hudXp.textContent = String(overall.total_xp);
    els.hudAccuracy.textContent = `${overall.accuracy.toFixed(1)}%`;

    if (els.diffCountAll) {
      els.diffCountAll.textContent = String(diffCounts.all ?? data.total_questions ?? 0);
    }
    if (els.diffCountBeginner) {
      els.diffCountBeginner.textContent = String(diffCounts.beginner ?? 0);
    }
    if (els.diffCountIntermediate) {
      els.diffCountIntermediate.textContent = String(diffCounts.intermediate ?? 0);
    }
    if (els.diffCountHard) {
      els.diffCountHard.textContent = String(diffCounts.hard ?? 0);
    }

    const activeTotal =
      diff === "all"
        ? (diffCounts.all ?? data.total_questions ?? 0)
        : (diffCounts[diff] ?? 0);
    const activeMissed =
      diff === "all"
        ? (missedByDiff.all ?? overall.missed_count ?? 0)
        : (missedByDiff[diff] ?? 0);

    els.allCount.textContent = String(activeTotal);
    els.missedCount.textContent = String(activeMissed);
    els.btnStartMissed.disabled = activeMissed === 0;
    els.overallAnswered.textContent = String(overall.answered);
    els.overallCorrect.textContent = String(overall.correct);
    if (els.tabLabsCount) {
      const compLabs = (data.completed_labs || []).length;
      const totLabs = data.total_labs ?? 10;
      els.tabLabsCount.textContent = `${compLabs}/${totLabs}`;
    }
    renderCustomMixBuilder(data);
    renderExamHistory(data.mock_exam_history || []);

    const tierLabels = {
      beginner: "Beginner",
      intermediate: "Intermediate",
      hard: "Hard",
    };

    els.categoriesGrid.innerHTML = "";
    data.categories.forEach((cat) => {
      const card = document.createElement("article");
      card.className = "skill-card";

      const head = document.createElement("div");
      head.className = "skill-card-head";
      const title = document.createElement("h3");
      title.className = "skill-name";
      title.textContent = cat.name;
      const lvl = document.createElement("span");
      lvl.className = "skill-level-badge";
      lvl.textContent = `Lv. ${cat.skill.level} / 99`;
      head.append(title, lvl);

      const diffs = cat.difficulties || {};
      const beg = diffs.beginner || { total: 0, answered: 0, unique_answered: 0, correct: 0, accuracy: 0 };
      const intr = diffs.intermediate || { total: 0, answered: 0, unique_answered: 0, correct: 0, accuracy: 0 };
      const hrd = diffs.hard || { total: 0, answered: 0, unique_answered: 0, correct: 0, accuracy: 0 };

      const statsRow = document.createElement("div");
      statsRow.className = "skill-stats-row";
      const accSpan = document.createElement("span");
      accSpan.innerHTML = "Accuracy: <strong></strong>";
      const ansSpan = document.createElement("span");
      ansSpan.innerHTML = "Answered: <strong></strong>";

      const xpWrap = document.createElement("div");
      xpWrap.className = "xp-bar-wrap";
      const track = document.createElement("div");

      if (diff === "all") {
        accSpan.querySelector("strong").textContent =
          cat.answered > 0 ? `${cat.accuracy.toFixed(1)}%` : "—";
        const uniqueTotal = cat.unique_answered ?? 0;
        ansSpan.querySelector("strong").textContent =
          `${cat.answered} (${uniqueTotal}/${cat.question_count} Qs)`;

        track.className = "xp-track segmented-progress-track";
        const denom = Math.max(1, cat.question_count || 1);
        const segSpecs = [
          { cls: "seg-beginner", count: beg.unique_answered || 0, title: `Beginner: ${beg.unique_answered}/${beg.total}` },
          { cls: "seg-intermediate", count: intr.unique_answered || 0, title: `Intermediate: ${intr.unique_answered}/${intr.total}` },
          { cls: "seg-hard", count: hrd.unique_answered || 0, title: `Hard: ${hrd.unique_answered}/${hrd.total}` },
        ];
        segSpecs.forEach((seg) => {
          const pct = Math.max(0, Math.min(100, (seg.count / denom) * 100));
          const segEl = document.createElement("div");
          segEl.className = `progress-seg ${seg.cls}`;
          segEl.style.width = `${pct.toFixed(2)}%`;
          segEl.title = seg.title;
          track.appendChild(segEl);
        });

        const mini = document.createElement("div");
        mini.className = "diff-mini-breakdown";
        [
          { dotCls: "dot-beginner", text: `Beg ${beg.unique_answered}/${beg.total}` },
          { dotCls: "dot-intermediate", text: `Int ${intr.unique_answered}/${intr.total}` },
          { dotCls: "dot-hard", text: `Hard ${hrd.unique_answered}/${hrd.total}` },
        ].forEach((item) => {
          const chip = document.createElement("span");
          chip.className = "diff-mini-item";
          const dot = document.createElement("span");
          dot.className = `diff-dot ${item.dotCls}`;
          const lbl = document.createElement("span");
          lbl.textContent = item.text;
          chip.append(dot, lbl);
          mini.appendChild(chip);
        });
        xpWrap.append(track, mini);
      } else {
        const tierData = diffs[diff] || { total: 0, answered: 0, unique_answered: 0, correct: 0, accuracy: 0 };
        accSpan.querySelector("strong").textContent =
          tierData.answered > 0 ? `${tierData.accuracy.toFixed(1)}%` : "—";
        ansSpan.querySelector("strong").textContent =
          `${tierData.unique_answered} / ${tierData.total} ${tierLabels[diff]} Qs`;

        track.className = "xp-track segmented-progress-track";
        const denom = Math.max(1, tierData.total || 1);
        const pct = Math.max(0, Math.min(100, ((tierData.unique_answered || 0) / denom) * 100));
        const fill = document.createElement("div");
        fill.className = `progress-seg seg-${diff}`;
        fill.style.width = `${pct.toFixed(2)}%`;
        track.appendChild(fill);
        xpWrap.appendChild(track);
      }

      statsRow.append(accSpan, ansSpan);

      const cap = document.createElement("div");
      cap.className = "xp-caption";
      const totalXpSpan = document.createElement("span");
      totalXpSpan.textContent = `${cat.skill.xp} Total XP`;
      const nextXpSpan = document.createElement("span");
      nextXpSpan.textContent = `${cat.skill.xp_in_level} / ${cat.skill.xp_for_next_level} XP`;
      cap.append(totalXpSpan, nextXpSpan);
      xpWrap.appendChild(cap);

      const actions = document.createElement("div");
      actions.className = "skill-card-actions";

      const launchBtn = document.createElement("button");
      launchBtn.type = "button";
      launchBtn.className = "btn btn-primary";
      launchBtn.textContent = "Train Category";
      launchBtn.addEventListener("click", () => {
        startQuiz({ scope: "category", category: cat.name });
      });

      const resetBtn = document.createElement("button");
      resetBtn.type = "button";
      resetBtn.className = "btn btn-danger btn-sm";
      resetBtn.textContent = "Reset";
      resetBtn.title = `Reset score for ${cat.name}`;
      resetBtn.addEventListener("click", () => {
        openResetModal(true, cat.name);
      });

      actions.append(launchBtn, resetBtn);
      card.append(head, statsRow, xpWrap, actions);
      els.categoriesGrid.appendChild(card);
    });
  }

  function renderLabsGrid(labs) {
    state.labs = labs || [];
    const completedCount = state.labs.filter((lab) => lab.completed).length;
    if (els.labsCompletedCount) {
      els.labsCompletedCount.textContent = String(completedCount);
    }
    if (els.labsTotalCount) {
      els.labsTotalCount.textContent = String(state.labs.length);
    }
    if (!els.labsGrid) return;

    els.labsGrid.innerHTML = "";
    state.labs.forEach((lab) => {
      const card = document.createElement("article");
      card.className = `lab-card${lab.completed ? " is-completed" : ""}`;

      const head = document.createElement("div");
      head.className = "lab-card-head";
      const title = document.createElement("h3");
      title.className = "skill-name";
      title.textContent = lab.title;

      const statusBadge = document.createElement("span");
      statusBadge.className = `lab-completed-badge${lab.completed ? " done" : ""}`;
      statusBadge.textContent = lab.completed ? "✓ Completed" : "○ Pending";
      head.append(title, statusBadge);

      const meta = document.createElement("div");
      meta.className = "lab-card-meta";
      const diffBadge = document.createElement("span");
      diffBadge.className = "badge badge-difficulty";
      diffBadge.dataset.difficulty = lab.difficulty;
      diffBadge.textContent = lab.difficulty.toUpperCase();
      const domainBadge = document.createElement("span");
      domainBadge.className = "badge badge-domain";
      domainBadge.textContent = lab.domain;
      meta.append(diffBadge, domainBadge);

      const desc = document.createElement("p");
      desc.className = "lab-card-objective";
      desc.textContent = lab.objective;

      const actions = document.createElement("div");
      actions.className = "skill-card-actions";
      const launchBtn = document.createElement("button");
      launchBtn.type = "button";
      launchBtn.className = "btn btn-primary";
      launchBtn.textContent = lab.completed ? "Practice Again" : "Launch Lab";
      launchBtn.addEventListener("click", () => startLab(lab.id));
      actions.appendChild(launchBtn);

      card.append(head, meta, desc, actions);
      els.labsGrid.appendChild(card);
    });
  }

  function getBackendLabel(backendId) {
    const labels =
      (state.sandboxCapabilities && state.sandboxCapabilities.backend_labels) || {
        native: "Native Bash",
        wsl: "WSL Linux",
        simulated: "Simulated Shell",
      };
    return labels[backendId] || backendId;
  }

  function renderBackendToggleInto(container, activeBackend, restartOnSelect) {
    if (!container || !state.sandboxCapabilities) return;
    const available = state.sandboxCapabilities.available_backends || [];
    container.innerHTML = "";
    available.forEach((backendId) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `backend-btn${backendId === activeBackend ? " active" : ""}`;
      btn.dataset.backend = backendId;
      btn.textContent = getBackendLabel(backendId);
      btn.addEventListener("click", () => {
        setSandboxBackend(backendId, { restartActiveLab: restartOnSelect });
      });
      container.appendChild(btn);
    });
  }

  function renderBackendControls() {
    if (!state.sandboxCapabilities) return;
    const available = state.sandboxCapabilities.available_backends || [];
    const active = available.includes(state.sandboxBackend)
      ? state.sandboxBackend
      : state.sandboxCapabilities.default_backend;
    state.sandboxBackend = active;
    const label = getBackendLabel(active);

    if (els.dashboardBackendBadge) {
      els.dashboardBackendBadge.textContent = label;
    }
    if (els.labBackendBadge) {
      const sessionBackend = state.activeLabSession && state.activeLabSession.backend;
      els.labBackendBadge.textContent = sessionBackend ? getBackendLabel(sessionBackend) : label;
    }

    renderBackendToggleInto(els.dashboardBackendToggle, active, false);
    const labActive =
      (state.activeLabSession && state.activeLabSession.backend) || active;
    renderBackendToggleInto(els.labBackendToggle, labActive, true);
  }

  function applySandboxCapabilities(caps) {
    state.sandboxCapabilities = caps;
    const available = caps.available_backends || [];
    let saved = null;
    try {
      saved = localStorage.getItem(BACKEND_KEY);
    } catch (e) {}
    if (saved && available.includes(saved)) {
      state.sandboxBackend = saved;
    } else if (!available.includes(state.sandboxBackend)) {
      state.sandboxBackend = caps.default_backend;
    }
    renderBackendControls();
  }

  async function setSandboxBackend(backendId, { restartActiveLab = false } = {}) {
    if (!state.sandboxCapabilities) return;
    const available = state.sandboxCapabilities.available_backends || [];
    if (!available.includes(backendId)) return;

    const previous = state.sandboxBackend;
    state.sandboxBackend = backendId;
    try {
      localStorage.setItem(BACKEND_KEY, backendId);
    } catch (e) {}
    renderBackendControls();

    if (restartActiveLab && state.activeLabSession && state.activeLabSession.backend !== backendId) {
      if (state.busy) {
        state.sandboxBackend = previous;
        renderBackendControls();
        return;
      }
      const currentLabId = state.activeLabSession.lab.id;
      const oldSessionId = state.activeLabSession.sessionId;
      try {
        await apiJson("/api/labs/close", {
          method: "POST",
          body: JSON.stringify({ session_id: oldSessionId }),
        });
      } catch (e) {}
      state.activeLabSession = null;
      await startLab(currentLabId);
    }
  }

  async function refreshDashboard() {
    try {
      const [data, labsPayload] = await Promise.all([
        apiJson("/api/state"),
        apiJson("/api/labs"),
      ]);
      renderDashboard(data);
      renderLabsGrid(labsPayload.labs || []);
      if (labsPayload.sandbox) {
        applySandboxCapabilities(labsPayload.sandbox);
      }
    } catch (err) {
      showAlert(err.message);
    }
  }

  function renderCurrentQuestion(payload) {
    state.awaitingNext = false;
    state.activeSession = {
      sessionId: payload.session_id || state.activeSession.sessionId,
      mode: payload.mode || state.activeSession.mode,
      scopeLabel: payload.scope_label || state.activeSession.scopeLabel,
      currentIndex: payload.current_index,
      totalQuestions: payload.total_questions,
      question: payload.question,
    };

    const q = payload.question;
    const mode = state.activeSession.mode;
    const progressPct = ((payload.current_index - 1) / payload.total_questions) * 100;

    els.quizScopeBadge.textContent = state.activeSession.scopeLabel;
    els.quizDomainBadge.textContent = q.domain;
    els.quizDifficultyBadge.textContent = q.difficulty.toUpperCase();
    els.quizDifficultyBadge.dataset.difficulty = q.difficulty;
    els.quizCounter.textContent = `Question ${payload.current_index} / ${payload.total_questions}`;
    els.sessionXp.textContent = String(payload.session_stats.xp_earned);
    els.quizProgressFill.style.width = `${progressPct}%`;
    els.questionPrompt.textContent = q.prompt;

    els.hintBox.classList.add("hidden");
    els.hintText.textContent = "";
    els.feedbackPanel.classList.add("hidden");

    if (mode === "multiple_choice") {
      els.mcContainer.classList.remove("hidden");
      els.exactContainer.classList.add("hidden");
      els.btnMcHint.disabled = false;
      els.btnMcSkip.disabled = false;
      els.mcOptions.innerHTML = "";

      const letters = ["A", "B", "C", "D"];
      letters.forEach((letter, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "mc-option";
        btn.dataset.letter = letter;

        const keyBadge = document.createElement("span");
        keyBadge.className = "mc-key";
        keyBadge.textContent = `${letter} / ${idx + 1}`;

        const textSpan = document.createElement("span");
        textSpan.textContent = q.choices[letter];

        btn.append(keyBadge, textSpan);
        btn.addEventListener("click", () => submitMultipleChoice(letter));
        els.mcOptions.appendChild(btn);
      });
    } else {
      els.mcContainer.classList.add("hidden");
      els.exactContainer.classList.remove("hidden");
      els.cmdInput.disabled = false;
      els.cmdInput.value = "";
      els.btnExactSubmit.disabled = false;
      els.btnExactHint.disabled = false;
      els.btnExactSkip.disabled = false;
      els.cmdInput.focus();
    }

    switchView("quiz");
  }

  async function startQuiz({ scope, category = null, categories = null, domains = null }) {
    if (state.busy) return;
    state.busy = true;
    showAlert("");
    state.lastStartParams = {
      scope,
      category,
      categories,
      domains,
      mode: state.mode,
      difficulty: state.difficulty,
      length: state.quizLength,
    };

    try {
      const data = await apiJson("/api/quiz/start", {
        method: "POST",
        body: JSON.stringify({
          scope,
          category,
          categories,
          domains,
          mode: state.mode,
          difficulty: state.difficulty,
          length: state.quizLength,
        }),
      });
      renderCurrentQuestion(data);
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function requestHint() {
    if (!state.activeSession || state.awaitingNext || state.busy) return;
    state.busy = true;
    try {
      const data = await apiJson("/api/quiz/hint", {
        method: "POST",
        body: JSON.stringify({ session_id: state.activeSession.sessionId }),
      });
      els.hintText.textContent = data.hint;
      els.hintBox.classList.remove("hidden");
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  function renderFeedback(result) {
    state.awaitingNext = true;

    if (result.dashboard) {
      renderDashboard(result.dashboard);
    }
    els.sessionXp.textContent = String(result.session_stats.xp_earned);
    const completedPct =
      (state.activeSession.currentIndex / state.activeSession.totalQuestions) * 100;
    els.quizProgressFill.style.width = `${completedPct}%`;

    if (state.activeSession.mode === "multiple_choice") {
      els.btnMcHint.disabled = true;
      els.btnMcSkip.disabled = true;
      els.mcOptions.querySelectorAll(".mc-option").forEach((btn) => {
        btn.disabled = true;
        const letter = btn.dataset.letter;
        if (letter === result.correct_letter) {
          btn.classList.add("is-correct");
        } else if (letter === result.selected_letter && !result.correct) {
          btn.classList.add("is-wrong");
        }
      });
    } else {
      els.cmdInput.disabled = true;
      els.btnExactSubmit.disabled = true;
      els.btnExactHint.disabled = true;
      els.btnExactSkip.disabled = true;
    }

    els.feedbackHitsplat.className = `hitsplat status-${result.status}`;
    if (result.status === "correct") {
      els.feedbackStatusLabel.textContent = "CORRECT";
      els.feedbackXpLabel.textContent = `+${result.xp_gained} XP`;
    } else if (result.status === "skipped") {
      els.feedbackStatusLabel.textContent = "SKIPPED";
      els.feedbackXpLabel.textContent = "0 XP";
    } else {
      els.feedbackStatusLabel.textContent = "INCORRECT";
      els.feedbackXpLabel.textContent = "0 XP";
    }

    if (result.user_answer && result.status === "incorrect") {
      els.feedbackUserAnswer.textContent = result.user_answer;
      els.feedbackUserAnswerRow.classList.remove("hidden");
    } else {
      els.feedbackUserAnswerRow.classList.add("hidden");
    }

    els.feedbackCorrectChoice.textContent = result.correct_choice;

    const extras = (result.accepted_commands || []).filter(
      (cmd) => cmd.trim() !== result.correct_choice.trim()
    );
    els.feedbackVariants.innerHTML = "";
    if (extras.length > 0) {
      extras.slice(0, 6).forEach((cmd) => {
        const chip = document.createElement("code");
        chip.className = "variant-chip";
        chip.textContent = cmd;
        els.feedbackVariants.appendChild(chip);
      });
      if (extras.length > 6) {
        const more = document.createElement("span");
        more.className = "shortcut-hint";
        more.textContent = `+${extras.length - 6} more`;
        els.feedbackVariants.appendChild(more);
      }
      els.feedbackVariantsRow.classList.remove("hidden");
    } else {
      els.feedbackVariantsRow.classList.add("hidden");
    }

    els.feedbackDomain.textContent = result.domain;
    els.feedbackExplanation.textContent = result.explanation;
    els.btnNextQuestion.textContent = result.is_last_question
      ? "View Session Summary (Enter) →"
      : "Next Question (Enter) →";

    els.feedbackPanel.classList.remove("hidden");
  }

  async function submitMultipleChoice(letter) {
    if (!state.activeSession || state.awaitingNext || state.busy) return;
    state.busy = true;
    showAlert("");
    try {
      const result = await apiJson("/api/quiz/answer", {
        method: "POST",
        body: JSON.stringify({
          session_id: state.activeSession.sessionId,
          choice: letter,
        }),
      });
      renderFeedback(result);
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function submitExactCommand(commandText) {
    if (!state.activeSession || state.awaitingNext || state.busy) return;
    const trimmed = commandText.trim();
    if (!trimmed) {
      showAlert("Type a Bash/POSIX command, 'hint', or 'skip'.");
      return;
    }

    state.busy = true;
    showAlert("");
    try {
      const result = await apiJson("/api/quiz/answer", {
        method: "POST",
        body: JSON.stringify({
          session_id: state.activeSession.sessionId,
          command: commandText,
        }),
      });
      if (result.status === "hint") {
        els.hintText.textContent = result.hint;
        els.hintBox.classList.remove("hidden");
        els.cmdInput.value = "";
        els.cmdInput.focus();
      } else {
        renderFeedback(result);
      }
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function skipQuestion() {
    if (!state.activeSession || state.awaitingNext || state.busy) return;
    state.busy = true;
    showAlert("");
    try {
      const result = await apiJson("/api/quiz/answer", {
        method: "POST",
        body: JSON.stringify({
          session_id: state.activeSession.sessionId,
          action: "skip",
        }),
      });
      renderFeedback(result);
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function nextQuestion() {
    if (!state.activeSession || !state.awaitingNext || state.busy) return;
    state.busy = true;
    showAlert("");
    try {
      const payload = await apiJson("/api/quiz/next", {
        method: "POST",
        body: JSON.stringify({ session_id: state.activeSession.sessionId }),
      });
      if (payload.completed) {
        state.activeSession = null;
        state.awaitingNext = false;
        renderDashboard(payload.dashboard);
        const s = payload.summary;
        els.summaryScopeText.textContent = `${payload.scope_label} (${
          payload.mode === "multiple_choice" ? "Multiple Choice" : "Exact Command Entry"
        })`;
        els.sumCorrect.textContent = `${s.correct} / ${s.total_questions}`;
        els.sumAccuracy.textContent = `${s.accuracy.toFixed(1)}%`;
        els.sumXp.textContent = `+${s.xp_earned} XP`;
        els.sumMeta.textContent = `${s.skipped} skipped / ${s.hints_used} hints`;
        els.btnSummaryMissed.classList.toggle(
          "hidden",
          payload.dashboard.overall.missed_count === 0
        );
        switchView("summary");
      } else {
        renderCurrentQuestion(payload);
      }
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  function openResetModal(show, category = null) {
    state.pendingResetCategory = show ? category : null;
    if (show) {
      if (category) {
        els.resetModalTitle.textContent = `Reset '${category}' Score?`;
        els.resetModalBody.textContent =
          `This will clear answered/correct counts, skill XP, and missed question IDs for '${category}' only.`;
      } else {
        els.resetModalTitle.textContent = "Reset All Study Progress?";
        els.resetModalBody.innerHTML =
          "This will permanently clear all per-category accuracy counters, skill XP levels, and your missed-questions queue in <code>data/progress.json</code>.";
      }
    }
    els.resetModal.classList.toggle("hidden", !show);
  }

  async function confirmResetProgress() {
    if (state.busy) return;
    state.busy = true;
    const category = state.pendingResetCategory;
    try {
      const payload = category ? { confirm: true, category } : { confirm: true };
      const data = await apiJson("/api/progress/reset", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      renderDashboard(data.dashboard);
      openResetModal(false);
      showAlert(
        category
          ? `Score and missed questions reset for '${category}'.`
          : "All study progress and missed queue have been reset."
      );
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  // -----------------------------------------------------------------------
  // Sandbox Lab Mode Functions
  // -----------------------------------------------------------------------

  function appendLabLine(text, cssClass) {
    if (!text) return;
    const line = document.createElement("div");
    line.className = `lab-term-line ${cssClass}`;
    line.textContent = text;
    els.labTerminalOutput.appendChild(line);
    els.labTerminalOutput.scrollTop = els.labTerminalOutput.scrollHeight;
  }

  function renderLabChecklist(items, verified = false) {
    els.labChecklist.innerHTML = "";
    items.forEach((item) => {
      const isObj = typeof item === "object" && item !== null;
      const desc = isObj ? item.description : String(item);
      const passed = isObj ? Boolean(item.passed) : false;

      const li = document.createElement("li");
      li.className = "lab-check-item";
      if (verified) {
        li.classList.add(passed ? "is-pass" : "is-fail");
      } else {
        li.classList.add("is-pending");
      }

      const icon = document.createElement("span");
      icon.className = "lab-check-icon";
      icon.textContent = verified ? (passed ? "✓" : "✗") : "○";

      const label = document.createElement("span");
      label.textContent = desc;

      li.append(icon, label);
      els.labChecklist.appendChild(li);
    });
  }

  function updateLabPrompt(cwd, prompt) {
    els.labCwdBadge.textContent = cwd || "~";
    els.labTerminalPrompt.textContent = prompt || "lab@sandbox:~$";
  }

  async function startLab(labId) {
    if (state.busy) return;
    state.busy = true;
    showAlert("");
    try {
      const data = await apiJson("/api/labs/start", {
        method: "POST",
        body: JSON.stringify({ lab_id: labId, backend: state.sandboxBackend }),
      });
      state.activeLabSession = {
        sessionId: data.session_id,
        lab: data.lab,
        backend: data.backend || state.sandboxBackend,
      };
      if (data.backend) {
        state.sandboxBackend = data.backend;
      }
      renderBackendControls();
      if (els.labBackendBadge && data.backend_label) {
        els.labBackendBadge.textContent = data.backend_label;
      }
      state.labCmdHistory = [];
      state.labHistoryIdx = -1;

      els.labTitleBadge.textContent = data.lab.title;
      els.labDomainBadge.textContent = data.lab.domain;
      els.labDifficultyBadge.textContent = data.lab.difficulty.toUpperCase();
      els.labDifficultyBadge.dataset.difficulty = data.lab.difficulty;
      els.labStatusBadge.textContent = data.lab.completed ? "COMPLETED" : "IN PROGRESS";
      els.labObjectiveText.textContent = data.lab.objective;

      els.labPassBanner.classList.add("hidden");
      els.labHintBox.classList.add("hidden");
      els.labHintText.textContent = "";
      els.labSolutionBox.classList.add("hidden");
      els.labSolutionCode.textContent = "";

      renderLabChecklist(data.lab.checklist, false);
      updateLabPrompt(data.cwd, data.prompt);

      els.labTerminalOutput.innerHTML = "";
      appendLabLine(
        `Isolated sandbox (${data.backend_label || getBackendLabel(state.sandboxBackend)}) initialized for "${data.lab.title}". Type Bash commands below, or 'check' to verify.`,
        "lab-term-system"
      );

      switchView("lab");
      els.labCmdInput.value = "";
      els.labCmdInput.focus();
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function execLabCommand(rawCommand) {
    if (!state.activeLabSession || state.busy) return;
    const trimmed = rawCommand.trim();
    if (!trimmed) return;

    state.labCmdHistory.push(rawCommand);
    state.labHistoryIdx = state.labCmdHistory.length;
    els.labCmdInput.value = "";

    const lowered = trimmed.toLowerCase();
    if (lowered === "clear") {
      els.labTerminalOutput.innerHTML = "";
      return;
    }
    if (lowered === "check") {
      await checkLabObjective();
      return;
    }
    if (lowered === "hint") {
      await fetchLabHint();
      return;
    }
    if (lowered === "reset") {
      await resetLabWorkspace();
      return;
    }
    if (lowered === "solution") {
      await fetchLabSolution();
      return;
    }

    appendLabLine(`${els.labTerminalPrompt.textContent} ${rawCommand}`, "lab-term-cmd");
    state.busy = true;
    try {
      const result = await apiJson("/api/labs/exec", {
        method: "POST",
        body: JSON.stringify({
          session_id: state.activeLabSession.sessionId,
          command: rawCommand,
        }),
      });
      if (result.stdout) {
        appendLabLine(result.stdout, "lab-term-stdout");
      }
      if (result.stderr) {
        appendLabLine(
          result.stderr,
          result.blocked ? "lab-term-warning" : "lab-term-stderr"
        );
      }
      updateLabPrompt(result.cwd, result.prompt);
    } catch (err) {
      appendLabLine(err.message, "lab-term-stderr");
    } finally {
      state.busy = false;
      els.labCmdInput.focus();
    }
  }

  async function checkLabObjective() {
    if (!state.activeLabSession || state.busy) return;
    state.busy = true;
    showAlert("");
    try {
      const result = await apiJson("/api/labs/check", {
        method: "POST",
        body: JSON.stringify({ session_id: state.activeLabSession.sessionId }),
      });
      renderLabChecklist(result.checks || [], true);
      if (result.passed) {
        els.labPassBanner.classList.remove("hidden");
        els.labStatusBadge.textContent = "PASSED";
        appendLabLine("✓ Verification passed! Lab marked completed.", "lab-term-system");
        if (result.dashboard) {
          renderDashboard(result.dashboard);
        }
      } else {
        els.labPassBanner.classList.add("hidden");
        appendLabLine("✗ Verification incomplete. Review the checklist on the left.", "lab-term-warning");
      }
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function resetLabWorkspace() {
    if (!state.activeLabSession || state.busy) return;
    state.busy = true;
    showAlert("");
    try {
      const result = await apiJson("/api/labs/reset", {
        method: "POST",
        body: JSON.stringify({ session_id: state.activeLabSession.sessionId }),
      });
      updateLabPrompt(result.cwd, result.prompt);
      renderLabChecklist(state.activeLabSession.lab.checklist, false);
      els.labPassBanner.classList.add("hidden");
      appendLabLine("Workspace reset to clean initial state.", "lab-term-system");
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
      els.labCmdInput.focus();
    }
  }

  async function fetchLabHint() {
    if (!state.activeLabSession || state.busy) return;
    state.busy = true;
    try {
      const result = await apiJson("/api/labs/hint", {
        method: "POST",
        body: JSON.stringify({ session_id: state.activeLabSession.sessionId }),
      });
      els.labHintText.textContent = result.hint;
      els.labHintBox.classList.remove("hidden");
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function fetchLabSolution() {
    if (!state.activeLabSession || state.busy) return;
    state.busy = true;
    try {
      const result = await apiJson("/api/labs/solution", {
        method: "POST",
        body: JSON.stringify({ session_id: state.activeLabSession.sessionId }),
      });
      els.labSolutionCode.textContent = result.solution_example;
      els.labSolutionBox.classList.remove("hidden");
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function closeLabSession() {
    const active = state.activeLabSession;
    state.activeLabSession = null;
    if (active) {
      try {
        await apiJson("/api/labs/close", {
          method: "POST",
          body: JSON.stringify({ session_id: active.sessionId }),
        });
      } catch (e) {}
    }
    showAlert("");
    await refreshDashboard();
    switchView("dashboard");
  }

  // Event Listeners
  els.themeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      applyTheme(btn.dataset.themeTarget, { clearColorOverrides: true });
    });
  });

  if (els.btnOpenCustomizer) {
    els.btnOpenCustomizer.addEventListener("click", () => openCustomizer(true));
  }
  if (els.btnCloseCustomizer) {
    els.btnCloseCustomizer.addEventListener("click", () => openCustomizer(false));
  }
  if (els.customizerBackdrop) {
    els.customizerBackdrop.addEventListener("click", () => openCustomizer(false));
  }
  els.presetBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      applyTheme(btn.dataset.themePreset, { clearColorOverrides: true });
    });
  });
  if (els.btnSaveCustom1) {
    els.btnSaveCustom1.addEventListener("click", () => saveCurrentLookToSlot("custom1"));
  }
  if (els.btnSaveCustom2) {
    els.btnSaveCustom2.addEventListener("click", () => saveCurrentLookToSlot("custom2"));
  }

  els.colorTargetBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeColorTarget = btn.dataset.colorTarget || "accent";
      syncColorEditor();
    });
  });

  els.colorModeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.colorEditorMode = btn.dataset.colorMode === "rgb" ? "rgb" : "hsb";
      syncColorEditor();
    });
  });

  function onHsbSliderInput() {
    const h = Number(els.sliderH ? els.sliderH.value : 0);
    const s = Number(els.sliderS ? els.sliderS.value : 0);
    const b = Number(els.sliderB ? els.sliderB.value : 0);
    const rgb = hsbToRgb(h, s, b);
    setActiveTargetColor(rgbToHex(rgb.r, rgb.g, rgb.b));
  }

  function onRgbSliderInput() {
    const r = Number(els.sliderR ? els.sliderR.value : 0);
    const g = Number(els.sliderG ? els.sliderG.value : 0);
    const b = Number(els.sliderBRgb ? els.sliderBRgb.value : 0);
    setActiveTargetColor(rgbToHex(r, g, b));
  }

  [els.sliderH, els.sliderS, els.sliderB].forEach((sl) => {
    if (sl) sl.addEventListener("input", onHsbSliderInput);
  });
  [els.sliderR, els.sliderG, els.sliderBRgb].forEach((sl) => {
    if (sl) sl.addEventListener("input", onRgbSliderInput);
  });
  if (els.editorHexInput) {
    els.editorHexInput.addEventListener("input", () => {
      const norm = normalizeHex(els.editorHexInput.value);
      if (norm) {
        setActiveTargetColor(norm);
      }
    });
  }

  if (els.customUiFont) {
    els.customUiFont.addEventListener("change", () => {
      applyCustomUi({ ...state.customUi, uiFont: els.customUiFont.value });
    });
  }
  if (els.customMonoFont) {
    els.customMonoFont.addEventListener("change", () => {
      applyCustomUi({ ...state.customUi, monoFont: els.customMonoFont.value });
    });
  }
  if (els.customFontScale) {
    els.customFontScale.addEventListener("input", () => {
      applyCustomUi({ ...state.customUi, fontScale: Number(els.customFontScale.value) });
    });
  }
  if (els.customRadius) {
    els.customRadius.addEventListener("input", () => {
      applyCustomUi({ ...state.customUi, radius: Number(els.customRadius.value) });
    });
  }
  if (els.customEffectsToggle) {
    els.customEffectsToggle.addEventListener("change", () => {
      applyCustomUi({ ...state.customUi, effects: els.customEffectsToggle.checked });
    });
  }
  els.densityBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      applyCustomUi({ ...state.customUi, density: btn.dataset.densityTarget });
    });
  });
  if (els.btnRandomizeCustomizer) {
    els.btnRandomizeCustomizer.addEventListener("click", randomizeAppearance);
  }
  if (els.btnResetCustomizer) {
    els.btnResetCustomizer.addEventListener("click", resetCustomizerToThemeDefaults);
  }

  els.modeMcBtn.addEventListener("click", () => applyMode("multiple_choice"));
  els.modeExactBtn.addEventListener("click", () => applyMode("exact_command"));
  els.diffBtns.forEach((btn) => {
    btn.addEventListener("click", () => applyDifficulty(btn.dataset.difficulty));
  });

  els.btnStartAll.addEventListener("click", () => startQuiz({ scope: "all" }));
  els.btnStartMissed.addEventListener("click", () => startQuiz({ scope: "missed" }));
  els.btnOpenReset.addEventListener("click", () => openResetModal(true));
  els.btnCancelReset.addEventListener("click", () => openResetModal(false));
  els.btnConfirmReset.addEventListener("click", confirmResetProgress);

  els.btnBackDashboard.addEventListener("click", () => {
    state.activeSession = null;
    state.awaitingNext = false;
    showAlert("");
    refreshDashboard();
    switchView("dashboard");
  });

  els.btnMcHint.addEventListener("click", requestHint);
  els.btnMcSkip.addEventListener("click", skipQuestion);
  els.btnExactHint.addEventListener("click", requestHint);
  els.btnExactSkip.addEventListener("click", skipQuestion);

  els.exactForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitExactCommand(els.cmdInput.value);
  });

  els.btnNextQuestion.addEventListener("click", nextQuestion);

  els.btnTrainAgain.addEventListener("click", () => {
    if (state.lastStartParams) {
      applyMode(state.lastStartParams.mode);
      applyDifficulty(state.lastStartParams.difficulty || "all");
      applyQuizLength(state.lastStartParams.length || "all");
      startQuiz({
        scope: state.lastStartParams.scope,
        category: state.lastStartParams.category,
        categories: state.lastStartParams.categories,
        domains: state.lastStartParams.domains,
      });
    } else {
      switchView("dashboard");
    }
  });

  els.hubTabBtns.forEach((btn) => {
    btn.addEventListener("click", () => switchHubTab(btn.dataset.hubTab));
  });
  els.lengthBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      applyQuizLength(btn.dataset.length);
      if (state.dashboard) renderCustomMixBuilder(state.dashboard);
    });
  });
  if (els.btnToggleCustomMix) {
    els.btnToggleCustomMix.addEventListener("click", () => {
      const nowHidden = els.customMixBody.classList.toggle("hidden");
      els.btnToggleCustomMix.setAttribute("aria-expanded", nowHidden ? "false" : "true");
    });
  }
  if (els.btnClearCustomMix) {
    els.btnClearCustomMix.addEventListener("click", () => {
      state.customCategories = [];
      state.customDomains = [];
      if (state.dashboard) renderCustomMixBuilder(state.dashboard);
    });
  }
  if (els.btnStartCustomMix) {
    els.btnStartCustomMix.addEventListener("click", () => {
      startQuiz({
        scope: "custom",
        categories: state.customCategories,
        domains: state.customDomains,
      });
    });
  }

  if (els.btnExamExit) {
    els.btnExamExit.addEventListener("click", () => {
      stopExamTimer();
      state.activeExam = null;
      switchHubTab("exams");
      switchView("dashboard");
    });
  }
  if (els.btnExamFlag) els.btnExamFlag.addEventListener("click", toggleExamFlag);
  if (els.btnExamPrev) {
    els.btnExamPrev.addEventListener("click", () => {
      if (state.activeExam && state.activeExam.currentIndex > 0) {
        state.activeExam.currentIndex -= 1;
        renderExamQuestion();
      }
    });
  }
  if (els.btnExamNext) {
    els.btnExamNext.addEventListener("click", () => {
      if (!state.activeExam) return;
      if (state.activeExam.currentIndex < state.activeExam.questions.length - 1) {
        state.activeExam.currentIndex += 1;
        renderExamQuestion();
      } else {
        openExamSubmitModal(true);
      }
    });
  }
  if (els.btnExamSubmitOpen) {
    els.btnExamSubmitOpen.addEventListener("click", () => openExamSubmitModal(true));
  }
  if (els.btnCancelExamSubmit) {
    els.btnCancelExamSubmit.addEventListener("click", () => openExamSubmitModal(false));
  }
  if (els.btnConfirmExamSubmit) {
    els.btnConfirmExamSubmit.addEventListener("click", () => submitMockExam({ timedOut: false }));
  }
  if (els.btnScorecardRetake) {
    els.btnScorecardRetake.addEventListener("click", () => {
      if (state.lastScorecard && state.lastScorecard.preset_id) {
        startMockExam(state.lastScorecard.preset_id);
      }
    });
  }
  if (els.btnScorecardDashboard) {
    els.btnScorecardDashboard.addEventListener("click", () => {
      switchHubTab("exams");
      switchView("dashboard");
    });
  }
  els.reviewFilterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.reviewFilter = btn.dataset.reviewFilter || "all";
      els.reviewFilterBtns.forEach((b) =>
        b.classList.toggle("active", b.dataset.reviewFilter === state.reviewFilter)
      );
      renderScorecardReviewList();
    });
  });

  els.btnSummaryMissed.addEventListener("click", () => startQuiz({ scope: "missed" }));
  els.btnSummaryDashboard.addEventListener("click", () => {
    refreshDashboard();
    switchView("dashboard");
  });

  function renderCustomMixBuilder(data) {
    if (!els.customMixCategories || !els.customMixDomains) return;
    els.customMixCategories.innerHTML = "";
    (data.categories || []).forEach((cat) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const active = state.customCategories.includes(cat.name);
      btn.className = `mix-chip${active ? " active" : ""}`;
      btn.textContent = `${cat.name} (${cat.question_count})`;
      btn.addEventListener("click", () => {
        if (state.customCategories.includes(cat.name)) {
          state.customCategories = state.customCategories.filter((c) => c !== cat.name);
        } else {
          state.customCategories = [...state.customCategories, cat.name];
        }
        renderCustomMixBuilder(state.dashboard);
      });
      els.customMixCategories.appendChild(btn);
    });

    els.customMixDomains.innerHTML = "";
    (data.domains || []).forEach((dom) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const active = state.customDomains.includes(dom.name);
      btn.className = `mix-chip${active ? " active" : ""}`;
      btn.textContent = `${dom.name} (${dom.weight}%)`;
      btn.addEventListener("click", () => {
        if (state.customDomains.includes(dom.name)) {
          state.customDomains = state.customDomains.filter((d) => d !== dom.name);
        } else {
          state.customDomains = [...state.customDomains, dom.name];
        }
        renderCustomMixBuilder(state.dashboard);
      });
      els.customMixDomains.appendChild(btn);
    });

    const catCount = state.customCategories.length;
    const domCount = state.customDomains.length;
    const hasSelection = catCount > 0 || domCount > 0;
    if (els.btnStartCustomMix) els.btnStartCustomMix.disabled = !hasSelection;
    if (els.customMixSummary) {
      els.customMixSummary.textContent = hasSelection
        ? `Selected: ${catCount} categor${catCount === 1 ? "y" : "ies"}, ${domCount} domain${domCount === 1 ? "" : "s"} • Length: ${state.quizLength.toUpperCase()}`
        : "Select categories or domains above to build a mix.";
    }
  }

  function renderExamHistory(history) {
    if (!els.examHistoryList) return;
    if (els.examAttemptsCount) {
      els.examAttemptsCount.textContent = String(history.length);
    }
    els.examHistoryList.innerHTML = "";
    if (!history.length) {
      const empty = document.createElement("p");
      empty.className = "panel-desc";
      empty.textContent = "No completed mock exams yet. Launch Mock Exam A, B, or C above to test your readiness.";
      els.examHistoryList.appendChild(empty);
      return;
    }
    history.slice(0, 12).forEach((entry) => {
      const row = document.createElement("div");
      row.className = "exam-history-row";
      const left = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = entry.title || entry.preset_id;
      const ts = document.createElement("span");
      ts.className = "shortcut-hint";
      ts.textContent = ` • ${entry.timestamp || ""}`;
      left.append(title, ts);

      const right = document.createElement("div");
      right.className = "exam-history-score";
      const badge = entry.passed ? "PASS" : "FAIL";
      right.textContent = `${entry.scaled_score}/900 (${badge}) • ${entry.correct}/${entry.total} (${entry.accuracy}%)`;
      row.append(left, right);
      els.examHistoryList.appendChild(row);
    });
  }

  function renderExamsHub(meta) {
    state.examsMeta = meta;
    if (els.examWeightsBar) {
      els.examWeightsBar.innerHTML = "";
      (meta.domains || []).forEach((d) => {
        const pill = document.createElement("span");
        pill.className = "exam-weight-pill";
        pill.innerHTML = `<strong>${d.weight}%</strong> ${d.name}`;
        els.examWeightsBar.appendChild(pill);
      });
    }
    if (els.examPresetsGrid) {
      els.examPresetsGrid.innerHTML = "";
      (meta.presets || []).forEach((preset) => {
        const card = document.createElement("article");
        card.className = "exam-preset-card";
        const top = document.createElement("div");
        const title = document.createElement("h3");
        title.className = "skill-name";
        title.textContent = preset.title;
        const desc = document.createElement("p");
        desc.className = "panel-desc";
        desc.textContent = preset.subtitle;
        top.append(title, desc);

        const metaRow = document.createElement("div");
        metaRow.className = "exam-preset-meta";
        metaRow.innerHTML = `<span class="exam-preset-badge">${preset.question_count} Questions</span><span class="exam-preset-badge">${preset.duration_minutes} Minutes</span>`;

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-primary";
        btn.textContent = `Start ${preset.title}`;
        btn.addEventListener("click", () => startMockExam(preset.id));

        card.append(top, metaRow, btn);
        els.examPresetsGrid.appendChild(card);
      });
    }
    renderExamHistory(meta.history || []);
  }

  async function loadExamsMeta() {
    try {
      const meta = await apiJson("/api/exams");
      renderExamsHub(meta);
    } catch (err) {
      // Non-fatal on initial load
    }
  }

  function formatSeconds(sec) {
    const clamped = Math.max(0, Math.floor(sec));
    const mins = Math.floor(clamped / 60);
    const rem = clamped % 60;
    return `${String(mins).padStart(2, "0")}:${String(rem).padStart(2, "0")}`;
  }

  function stopExamTimer() {
    if (state.examTimerInterval) {
      clearInterval(state.examTimerInterval);
      state.examTimerInterval = null;
    }
  }

  function updateExamTimerDisplay() {
    if (!state.activeExam || !els.examTimerDisplay) return;
    const rem = state.activeExam.remainingSeconds;
    els.examTimerDisplay.textContent = formatSeconds(rem);
    els.examTimerDisplay.classList.toggle("is-warning", rem <= 600 && rem > 120);
    els.examTimerDisplay.classList.toggle("is-critical", rem <= 120);
  }

  function startExamTimer() {
    stopExamTimer();
    updateExamTimerDisplay();
    state.examTimerInterval = setInterval(() => {
      if (!state.activeExam) {
        stopExamTimer();
        return;
      }
      state.activeExam.remainingSeconds -= 1;
      updateExamTimerDisplay();
      if (state.activeExam.remainingSeconds <= 0) {
        stopExamTimer();
        submitMockExam({ timedOut: true });
      }
    }, 1000);
  }

  function renderExamNavigator() {
    if (!state.activeExam || !els.examNavigatorGrid) return;
    const exam = state.activeExam;
    const answeredCount = Object.keys(exam.answers).length;
    if (els.examNavCounts) {
      els.examNavCounts.textContent = `${answeredCount} / ${exam.questions.length} answered`;
    }
    els.examNavigatorGrid.innerHTML = "";
    exam.questions.forEach((q, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "exam-nav-btn";
      if (idx === exam.currentIndex) btn.classList.add("is-current");
      if (q.id in exam.answers) btn.classList.add("is-answered");
      if (exam.flaggedIds.has(q.id)) btn.classList.add("is-flagged");
      btn.textContent = String(idx + 1);
      btn.addEventListener("click", () => {
        exam.currentIndex = idx;
        renderExamQuestion();
      });
      els.examNavigatorGrid.appendChild(btn);
    });
  }

  function renderExamQuestion() {
    const exam = state.activeExam;
    if (!exam) return;
    const q = exam.questions[exam.currentIndex];
    els.examTitleBadge.textContent = exam.title;
    els.examDomainBadge.textContent = q.domain;
    els.examDifficultyBadge.textContent = q.difficulty ? q.difficulty.toUpperCase() : "STANDARD";
    els.examCounter.textContent = `Question ${exam.currentIndex + 1} / ${exam.questions.length}`;
    els.examQNum.textContent = String(exam.currentIndex + 1);
    els.examQuestionPrompt.textContent = q.prompt;

    const isFlagged = exam.flaggedIds.has(q.id);
    els.btnExamFlag.classList.toggle("btn-flagged", isFlagged);
    els.btnExamFlag.textContent = isFlagged ? "★ Flagged" : "⚑ Flag for Review";

    const selectedIdx = exam.answers[q.id];
    const letters = ["A", "B", "C", "D"];
    els.examMcOptions.innerHTML = "";
    (q.choices || []).forEach((choiceText, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `mc-option${selectedIdx === idx ? " is-selected" : ""}`;
      btn.innerHTML = `<span class="mc-letter">${letters[idx]}</span><span class="mc-text"></span>`;
      btn.querySelector(".mc-text").textContent = choiceText;
      btn.addEventListener("click", () => selectExamChoice(idx));
      els.examMcOptions.appendChild(btn);
    });

    els.btnExamPrev.disabled = exam.currentIndex === 0;
    els.btnExamNext.textContent =
      exam.currentIndex >= exam.questions.length - 1 ? "Review / Submit →" : "Next →";

    renderExamNavigator();
  }

  async function startMockExam(presetId) {
    if (state.busy) return;
    state.busy = true;
    showAlert("");
    try {
      const data = await apiJson("/api/exams/start", {
        method: "POST",
        body: JSON.stringify({ preset: presetId }),
      });
      state.activeExam = {
        examSessionId: data.exam_session_id,
        presetId: data.preset_id,
        title: data.title,
        subtitle: data.subtitle,
        durationSeconds: data.duration_seconds,
        remainingSeconds: data.duration_seconds,
        questions: data.questions,
        currentIndex: 0,
        answers: {},
        flaggedIds: new Set(),
      };
      renderExamQuestion();
      switchView("exam");
      startExamTimer();
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  async function selectExamChoice(choiceIdx) {
    const exam = state.activeExam;
    if (!exam) return;
    const q = exam.questions[exam.currentIndex];
    exam.answers[q.id] = choiceIdx;
    renderExamQuestion();
    try {
      await apiJson("/api/exams/answer", {
        method: "POST",
        body: JSON.stringify({
          exam_session_id: exam.examSessionId,
          question_id: q.id,
          selected_index: choiceIdx,
        }),
      });
    } catch (e) {}
  }

  async function toggleExamFlag() {
    const exam = state.activeExam;
    if (!exam) return;
    const q = exam.questions[exam.currentIndex];
    const nowFlagged = !exam.flaggedIds.has(q.id);
    if (nowFlagged) {
      exam.flaggedIds.add(q.id);
    } else {
      exam.flaggedIds.delete(q.id);
    }
    renderExamQuestion();
    try {
      await apiJson("/api/exams/answer", {
        method: "POST",
        body: JSON.stringify({
          exam_session_id: exam.examSessionId,
          question_id: q.id,
          flagged: nowFlagged,
        }),
      });
    } catch (e) {}
  }

  function openExamSubmitModal(open) {
    if (!els.examSubmitModal) return;
    if (open && state.activeExam) {
      const total = state.activeExam.questions.length;
      const answered = Object.keys(state.activeExam.answers).length;
      const unanswered = total - answered;
      els.examSubmitModalBody.textContent =
        unanswered > 0
          ? `You have ${unanswered} unanswered question(s) out of ${total}. Submit and score anyway?`
          : `All ${total} questions answered. Ready to submit and view your XK0-006 scorecard?`;
    }
    els.examSubmitModal.classList.toggle("hidden", !open);
  }

  async function submitMockExam({ timedOut = false } = {}) {
    const exam = state.activeExam;
    if (!exam || state.busy) return;
    state.busy = true;
    openExamSubmitModal(false);
    stopExamTimer();
    const elapsedSeconds = Math.max(0, exam.durationSeconds - exam.remainingSeconds);
    try {
      const data = await apiJson("/api/exams/submit", {
        method: "POST",
        body: JSON.stringify({
          exam_session_id: exam.examSessionId,
          answers: exam.answers,
          flagged_ids: Array.from(exam.flaggedIds),
          elapsed_seconds: elapsedSeconds,
          timed_out: timedOut,
        }),
      });
      state.activeExam = null;
      if (data.dashboard) renderDashboard(data.dashboard);
      loadExamsMeta();
      renderExamScorecard(data);
    } catch (err) {
      showAlert(err.message);
    } finally {
      state.busy = false;
    }
  }

  function renderScorecardReviewList() {
    if (!state.lastScorecard || !els.scorecardReviewList) return;
    const filter = state.reviewFilter || "all";
    const items = (state.lastScorecard.review_items || []).filter((item) => {
      if (filter === "missed") return !item.is_correct;
      if (filter === "flagged") return item.is_flagged;
      return true;
    });
    els.scorecardReviewList.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "panel-desc";
      empty.textContent = `No ${filter} items to display.`;
      els.scorecardReviewList.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = `review-item-card ${item.is_correct ? "is-correct" : "is-wrong"}`;
      const head = document.createElement("div");
      head.className = "review-item-head";
      head.textContent = `#${item.number} • ${item.domain} • ${item.is_correct ? "CORRECT" : "INCORRECT"}${item.is_flagged ? " • ★ FLAGGED" : ""}`;
      const prompt = document.createElement("p");
      prompt.className = "review-item-prompt";
      prompt.textContent = item.prompt;
      const ans = document.createElement("p");
      ans.className = "review-item-answers";
      ans.textContent = `Your answer: ${item.selected_text || "(Unanswered)"}  |  Correct: ${item.correct_text}`;
      const exp = document.createElement("p");
      exp.className = "review-item-exp";
      exp.textContent = item.explanation;
      card.append(head, prompt, ans, exp);
      els.scorecardReviewList.appendChild(card);
    });
  }

  function renderExamScorecard(data) {
    state.lastScorecard = data;
    state.reviewFilter = "all";
    els.scorecardSubtitle.textContent = data.timed_out
      ? "Time Expired — Auto-Submitted"
      : data.subtitle || "Mock Exam Complete";
    els.scorecardTitle.textContent = data.title;
    els.scorecardPassBadge.textContent = data.passed ? "PASS" : "FAIL";
    els.scorecardPassBadge.className = `scorecard-pass-badge ${data.passed ? "is-pass" : "is-fail"}`;
    els.scorecardScaled.textContent = String(data.scaled_score);
    els.scorecardCorrect.textContent = `${data.correct} / ${data.total}`;
    els.scorecardAccuracy.textContent = `${Number(data.accuracy).toFixed(1)}%`;
    els.scorecardAnswered.textContent = `${data.answered} / ${data.total}`;
    els.scorecardTime.textContent =
      data.elapsed_seconds != null ? formatSeconds(data.elapsed_seconds) : "—";

    els.scorecardDomainBars.innerHTML = "";
    (data.domain_breakdown || []).forEach((dom) => {
      const row = document.createElement("div");
      row.className = "scorecard-domain-row";
      const meta = document.createElement("div");
      meta.className = "scorecard-domain-meta";
      meta.innerHTML = `<span>${dom.domain} (${dom.weight}%)</span><strong>${dom.correct}/${dom.total} (${dom.accuracy}%)</strong>`;
      const track = document.createElement("div");
      track.className = "xp-track";
      const fill = document.createElement("div");
      fill.className = "xp-fill";
      fill.style.width = `${dom.accuracy}%`;
      track.appendChild(fill);
      row.append(meta, track);
      els.scorecardDomainBars.appendChild(row);
    });

    els.reviewFilterBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.reviewFilter === "all");
    });
    renderScorecardReviewList();
    switchView("exam-scorecard");
  }

  // Sandbox Lab Event Listeners
  els.btnLabBack.addEventListener("click", closeLabSession);
  els.btnLabCheck.addEventListener("click", checkLabObjective);
  els.btnLabHint.addEventListener("click", fetchLabHint);
  els.btnLabReset.addEventListener("click", resetLabWorkspace);
  els.btnLabSolution.addEventListener("click", fetchLabSolution);
  els.labCmdForm.addEventListener("submit", (event) => {
    event.preventDefault();
    execLabCommand(els.labCmdInput.value);
  });
  els.labCmdInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp") {
      if (state.labCmdHistory.length > 0 && state.labHistoryIdx > 0) {
        event.preventDefault();
        state.labHistoryIdx -= 1;
        els.labCmdInput.value = state.labCmdHistory[state.labHistoryIdx];
      }
    } else if (event.key === "ArrowDown") {
      if (state.labHistoryIdx < state.labCmdHistory.length - 1) {
        event.preventDefault();
        state.labHistoryIdx += 1;
        els.labCmdInput.value = state.labCmdHistory[state.labHistoryIdx];
      } else if (state.labHistoryIdx === state.labCmdHistory.length - 1) {
        event.preventDefault();
        state.labHistoryIdx = state.labCmdHistory.length;
        els.labCmdInput.value = "";
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (els.customizerDrawer && !els.customizerDrawer.classList.contains("hidden")) {
      if (event.key === "Escape") {
        openCustomizer(false);
      }
      return;
    }

    if (!els.resetModal.classList.contains("hidden")) {
      if (event.key === "Escape") {
        openResetModal(false);
      }
      return;
    }

    if (els.quizView.classList.contains("hidden") || !state.activeSession) {
      return;
    }

    if (state.awaitingNext) {
      if (event.key === "Enter") {
        event.preventDefault();
        nextQuestion();
      }
      return;
    }

    if (state.activeSession.mode === "multiple_choice") {
      const keyMap = {
        "1": "A",
        "2": "B",
        "3": "C",
        "4": "D",
        a: "A",
        b: "B",
        c: "C",
        d: "D",
      };
      const lowered = event.key.toLowerCase();
      if (lowered in keyMap) {
        event.preventDefault();
        submitMultipleChoice(keyMap[lowered]);
      } else if (lowered === "h") {
        event.preventDefault();
        requestHint();
      }
    }
  });

  // Init
  let savedTheme = "cyberpunk";
  let savedMode = "multiple_choice";
  let savedDifficulty = "all";
  let savedQuizLength = "all";
  let savedHubTab = "practice";
  let savedCustomUi = null;
  try {
    savedTheme = localStorage.getItem(THEME_KEY) || "cyberpunk";
    savedMode = localStorage.getItem(MODE_KEY) || "multiple_choice";
    savedDifficulty = localStorage.getItem(DIFFICULTY_KEY) || "all";
    savedQuizLength = localStorage.getItem(QUIZ_LENGTH_KEY) || "all";
    savedHubTab = localStorage.getItem(HUB_TAB_KEY) || "practice";
    const rawCustom = localStorage.getItem(CUSTOM_UI_KEY);
    if (rawCustom) {
      savedCustomUi = JSON.parse(rawCustom);
    }
    const rawSlots = localStorage.getItem(CUSTOM_SLOTS_KEY);
    if (rawSlots) {
      const parsedSlots = JSON.parse(rawSlots);
      if (parsedSlots && typeof parsedSlots === "object") {
        state.customSlots = parsedSlots;
      }
    }
  } catch (e) {}

  applyTheme(savedTheme);
  if (savedCustomUi && typeof savedCustomUi === "object") {
    applyCustomUi(savedCustomUi, { save: false });
  } else {
    syncCustomizerInputs();
  }
  applyMode(savedMode);
  applyDifficulty(savedDifficulty);
  applyQuizLength(savedQuizLength);
  switchHubTab(savedHubTab);
  refreshDashboard();
  loadExamsMeta();
})();
