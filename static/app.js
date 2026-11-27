(() => {
  "use strict";

  const THEME_KEY = "linux_plus_theme";
  const MODE_KEY = "linux_plus_mode";
  const DIFFICULTY_KEY = "linux_plus_difficulty";
  const BACKEND_KEY = "linux_plus_sandbox_backend";

  const state = {
    theme: "cyberpunk",
    mode: "multiple_choice",
    difficulty: "all",
    sandboxBackend: "auto",
    sandboxCapabilities: null,
    dashboard: null,
    labs: [],
    activeSession: null,
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
    btnThemeOsrs: document.getElementById("btn-theme-osrs"),
    btnThemeCyberpunk: document.getElementById("btn-theme-cyberpunk"),
    btnThemeOot: document.getElementById("btn-theme-oot"),

    dashboardView: document.getElementById("dashboard-view"),
    quizView: document.getElementById("quiz-view"),
    labView: document.getElementById("lab-view"),
    summaryView: document.getElementById("summary-view"),

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

  function applyTheme(theme) {
    const valid = theme === "osrs" || theme === "oot" ? theme : "cyberpunk";
    state.theme = valid;
    document.documentElement.dataset.theme = valid;
    try {
      localStorage.setItem(THEME_KEY, valid);
    } catch (e) {}
    els.btnThemeOsrs.classList.toggle("active", valid === "osrs");
    els.btnThemeCyberpunk.classList.toggle("active", valid === "cyberpunk");
    els.btnThemeOot.classList.toggle("active", valid === "oot");
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
  }

  function switchView(viewName) {
    els.dashboardView.classList.toggle("hidden", viewName !== "dashboard");
    els.quizView.classList.toggle("hidden", viewName !== "quiz");
    els.labView.classList.toggle("hidden", viewName !== "lab");
    els.summaryView.classList.toggle("hidden", viewName !== "summary");
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

    els.hudLevel.textContent = String(overall.total_level);
    els.hudXp.textContent = String(overall.total_xp);
    els.hudAccuracy.textContent = `${overall.accuracy.toFixed(1)}%`;

    els.allCount.textContent = String(data.total_questions);
    els.missedCount.textContent = String(overall.missed_count);
    els.btnStartMissed.disabled = overall.missed_count === 0;
    els.overallAnswered.textContent = String(overall.answered);
    els.overallCorrect.textContent = String(overall.correct);

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

      const statsRow = document.createElement("div");
      statsRow.className = "skill-stats-row";
      const accSpan = document.createElement("span");
      accSpan.innerHTML = "Accuracy: <strong></strong>";
      accSpan.querySelector("strong").textContent =
        cat.answered > 0 ? `${cat.accuracy.toFixed(1)}%` : "—";
      const ansSpan = document.createElement("span");
      ansSpan.innerHTML = "Answered: <strong></strong>";
      ansSpan.querySelector("strong").textContent = `${cat.answered} (${cat.question_count} Qs)`;
      statsRow.append(accSpan, ansSpan);

      const xpWrap = document.createElement("div");
      xpWrap.className = "xp-bar-wrap";
      const track = document.createElement("div");
      track.className = "xp-track";
      const fill = document.createElement("div");
      fill.className = "xp-fill";
      fill.style.width = `${cat.skill.xp_percent}%`;
      track.appendChild(fill);

      const cap = document.createElement("div");
      cap.className = "xp-caption";
      const totalXpSpan = document.createElement("span");
      totalXpSpan.textContent = `${cat.skill.xp} Total XP`;
      const nextXpSpan = document.createElement("span");
      nextXpSpan.textContent = `${cat.skill.xp_in_level} / ${cat.skill.xp_for_next_level} XP`;
      cap.append(totalXpSpan, nextXpSpan);
      xpWrap.append(track, cap);

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

  async function startQuiz({ scope, category = null }) {
    if (state.busy) return;
    state.busy = true;
    showAlert("");
    state.lastStartParams = {
      scope,
      category,
      mode: state.mode,
      difficulty: state.difficulty,
    };

    try {
      const data = await apiJson("/api/quiz/start", {
        method: "POST",
        body: JSON.stringify({
          scope,
          category,
          mode: state.mode,
          difficulty: state.difficulty,
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
  els.btnThemeOsrs.addEventListener("click", () => applyTheme("osrs"));
  els.btnThemeCyberpunk.addEventListener("click", () => applyTheme("cyberpunk"));
  els.btnThemeOot.addEventListener("click", () => applyTheme("oot"));

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
      startQuiz({
        scope: state.lastStartParams.scope,
        category: state.lastStartParams.category,
      });
    } else {
      switchView("dashboard");
    }
  });

  els.btnSummaryMissed.addEventListener("click", () => startQuiz({ scope: "missed" }));
  els.btnSummaryDashboard.addEventListener("click", () => {
    refreshDashboard();
    switchView("dashboard");
  });

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
  try {
    savedTheme = localStorage.getItem(THEME_KEY) || "cyberpunk";
    savedMode = localStorage.getItem(MODE_KEY) || "multiple_choice";
    savedDifficulty = localStorage.getItem(DIFFICULTY_KEY) || "all";
  } catch (e) {}

  applyTheme(savedTheme);
  applyMode(savedMode);
  applyDifficulty(savedDifficulty);
  refreshDashboard();
})();
