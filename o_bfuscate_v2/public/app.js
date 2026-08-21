// public/app.js
// Client Controller for O_bfuscate V2 Web Dashboard

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const sourceCodeInput = document.getElementById('source-code');
  const outputCodeDisplay = document.getElementById('output-code');
  const sourceLineNumbers = document.getElementById('source-line-numbers');
  const outputLineNumbers = document.getElementById('output-line-numbers');
  const sourceStats = document.getElementById('source-stats');
  const outputStats = document.getElementById('output-stats');
  const btnObfuscate = document.getElementById('btn-obfuscate');
  const btnClear = document.getElementById('btn-clear');
  const btnCopy = document.getElementById('btn-copy');
  const btnDownload = document.getElementById('btn-download');
  const btnAstInspector = document.getElementById('btn-ast-inspector');
  const sampleSelector = document.getElementById('sample-selector');
  const toast = document.getElementById('toast');
  const toastMessage = document.getElementById('toast-message');
  const statusBadge = document.getElementById('status-badge');

  // Telemetry Elements
  const badgeSecScore = document.getElementById('badge-sec-score');
  const fillSecScore = document.getElementById('fill-sec-score');
  const badgePerfScore = document.getElementById('badge-perf-score');
  const fillPerfScore = document.getElementById('fill-perf-score');
  const valTimeMs = document.getElementById('val-time-ms');
  const valPassesCount = document.getElementById('val-passes-count');
  const valRatio = document.getElementById('val-ratio');
  const valBytesDiff = document.getElementById('val-bytes-diff');

  // Drawer
  const drawerHeader = document.getElementById('drawer-toggle-btn');
  const drawerBody = document.getElementById('drawer-content');

  // Modal
  const astModal = document.getElementById('ast-modal');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const astJsonView = document.getElementById('ast-json-view');

  // Presets Cards
  const presetCards = document.querySelectorAll('.preset-card');

  // Toggles
  const optNative = document.getElementById('opt-native');
  const optStringCrypto = document.getElementById('opt-string-crypto');
  const optLocalizeGlobals = document.getElementById('opt-localize-globals');
  const optIndirectMembers = document.getElementById('opt-indirect-members');
  const optMangler = document.getElementById('opt-mangler');
  const optMba = document.getElementById('opt-mba');
  const optCff = document.getElementById('opt-cff');
  const optOpaque = document.getElementById('opt-opaque');
  const optAntiTamper = document.getElementById('opt-antitamper');
  const optMinify = document.getElementById('opt-minify');
  const selectManglerMode = document.getElementById('select-mangler-mode');
  const inputWatermark = document.getElementById('input-watermark');

  let currentPreset = 'max-performance';
  let serverData = null;

  // Fetch initial info & samples from server
  fetch('/api/info')
    .then(res => res.json())
    .then(data => {
      serverData = data;
      // Load default sample
      if (data.samples && data.samples.raycast_aimbot) {
        sourceCodeInput.value = data.samples.raycast_aimbot.code;
        updateLineNumbers(sourceCodeInput, sourceLineNumbers, sourceStats);
      }
    })
    .catch(err => console.error('Failed to load server info:', err));

  // Sync Line Numbers
  function updateLineNumbers(textarea, lineContainer, statsElement) {
    const lines = textarea.value.split('\n').length;
    let numbersHtml = '';
    for (let i = 1; i <= Math.max(lines, 1); i++) {
      numbersHtml += `${i}<br>`;
    }
    lineContainer.innerHTML = numbersHtml;

    if (statsElement) {
      const bytes = new Blob([textarea.value]).size;
      statsElement.textContent = `Lines: ${lines} | Size: ${formatBytes(bytes)}`;
    }
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    return (bytes / 1024).toFixed(1) + ' KB';
  }

  sourceCodeInput.addEventListener('input', () => {
    updateLineNumbers(sourceCodeInput, sourceLineNumbers, sourceStats);
  });

  sourceCodeInput.addEventListener('scroll', () => {
    sourceLineNumbers.scrollTop = sourceCodeInput.scrollTop;
  });

  outputCodeDisplay.addEventListener('scroll', () => {
    outputLineNumbers.scrollTop = outputCodeDisplay.scrollTop;
  });

  // Drawer Toggle
  drawerHeader.addEventListener('click', () => {
    drawerHeader.classList.toggle('open');
    drawerBody.classList.toggle('open');
  });

  // Presets Handler
  const PRESET_CONFIGS = {
    'max-performance': {
      native: true,
      stringCrypto: true,
      localizeGlobals: true,
      indirectMembers: true,
      mangler: true,
      manglerMode: 'hex_hash',
      mba: true,
      cff: false,
      opaque: false,
      antiTamper: false,
      minify: true
    },
    'balanced': {
      native: true,
      stringCrypto: true,
      localizeGlobals: true,
      indirectMembers: true,
      mangler: true,
      manglerMode: 'barcode',
      mba: true,
      cff: true,
      opaque: true,
      antiTamper: true,
      minify: true
    },
    'ultra-secure': {
      native: true,
      stringCrypto: true,
      localizeGlobals: true,
      indirectMembers: true,
      mangler: true,
      manglerMode: 'confusables',
      mba: true,
      cff: true,
      opaque: true,
      antiTamper: true,
      minify: true
    }
  };

  function applyPreset(presetName) {
    currentPreset = presetName;
    presetCards.forEach(card => {
      card.classList.toggle('active', card.getAttribute('data-preset') === presetName);
    });

    if (presetName === 'custom') return;

    const cfg = PRESET_CONFIGS[presetName];
    if (cfg) {
      optNative.checked = cfg.native;
      optStringCrypto.checked = cfg.stringCrypto;
      optLocalizeGlobals.checked = cfg.localizeGlobals;
      optIndirectMembers.checked = cfg.indirectMembers;
      optMangler.checked = cfg.mangler;
      selectManglerMode.value = cfg.manglerMode;
      optMba.checked = cfg.mba;
      optCff.checked = cfg.cff;
      optOpaque.checked = cfg.opaque;
      optAntiTamper.checked = cfg.antiTamper;
      optMinify.checked = cfg.minify;
    }
  }

  presetCards.forEach(card => {
    card.addEventListener('click', () => {
      const p = card.getAttribute('data-preset');
      applyPreset(p);
    });
  });

  // Listen to manual checkbox changes to switch to Custom
  const allCheckboxes = [
    optNative, optStringCrypto, optLocalizeGlobals, optIndirectMembers,
    optMangler, optMba, optCff, optOpaque, optAntiTamper, optMinify
  ];
  allCheckboxes.forEach(cb => {
    cb.addEventListener('change', () => {
      presetCards.forEach(card => card.classList.remove('active'));
      document.getElementById('preset-custom').classList.add('active');
      currentPreset = 'custom';
    });
  });

  // Sample Selector
  sampleSelector.addEventListener('change', (e) => {
    const key = e.target.value;
    if (key && serverData && serverData.samples && serverData.samples[key]) {
      sourceCodeInput.value = serverData.samples[key].code;
      updateLineNumbers(sourceCodeInput, sourceLineNumbers, sourceStats);
      showToast(`Loaded "${serverData.samples[key].title}"`);
    }
  });

  // Clear Button
  btnClear.addEventListener('click', () => {
    sourceCodeInput.value = '';
    outputCodeDisplay.value = '';
    updateLineNumbers(sourceCodeInput, sourceLineNumbers, sourceStats);
    updateLineNumbers(outputCodeDisplay, outputLineNumbers, outputStats);
    sourceCodeInput.focus();
  });

  // Copy Button
  btnCopy.addEventListener('click', () => {
    if (!outputCodeDisplay.value.trim()) {
      showToast('Nothing to copy! Obfuscate some code first.', true);
      return;
    }
    navigator.clipboard.writeText(outputCodeDisplay.value)
      .then(() => showToast('Copied obfuscated code to clipboard!'))
      .catch(() => showToast('Failed to copy', true));
  });

  // Download Button
  btnDownload.addEventListener('click', () => {
    if (!outputCodeDisplay.value.trim()) {
      showToast('Nothing to download!', true);
      return;
    }
    const blob = new Blob([outputCodeDisplay.value], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `protected_script_${Date.now()}.obf.luau`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Download started!');
  });

  // Toast Helper
  function showToast(msg, isError = false) {
    toastMessage.textContent = msg;
    toast.style.borderColor = isError ? '#ff007f' : 'var(--accent-emerald)';
    toast.style.color = isError ? '#ff007f' : 'var(--accent-emerald)';
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 3000);
  }

  // Obfuscate Action
  async function performObfuscation() {
    const code = sourceCodeInput.value.trim();
    if (!code) {
      showToast('Please enter Luau source code to obfuscate!', true);
      return;
    }

    btnObfuscate.style.opacity = '0.7';
    btnObfuscate.style.pointerEvents = 'none';
    statusBadge.innerHTML = '<span class="status-dot" style="background:var(--accent-amber);"></span><span>Compiling...</span>';

    const options = {
      preset: currentPreset,
      watermark: inputWatermark.value || 'protected by O_bfuscate v2, created by Undix',
      nativeDirective: optNative.checked,
      optimizeDirective: optNative.checked,
      localizeGlobals: optLocalizeGlobals.checked,
      indirectMembers: optIndirectMembers.checked,
      stringCrypto: optStringCrypto.checked,
      mangler: optMangler.checked,
      manglerMode: selectManglerMode.value,
      mbaConstants: optMba.checked,
      controlFlow: optCff.checked,
      opaquePredicates: optOpaque.checked,
      antiTamper: optAntiTamper.checked,
      minify: optMinify.checked
    };

    try {
      const response = await fetch('/api/obfuscate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, options })
      });

      const data = await response.json();

      if (data.success) {
        outputCodeDisplay.value = data.code;
        updateLineNumbers(outputCodeDisplay, outputLineNumbers, outputStats);

        // Update telemetry
        const stats = data.stats;
        badgeSecScore.textContent = `${stats.securityRating}%`;
        fillSecScore.style.width = `${stats.securityRating}%`;

        badgePerfScore.textContent = stats.performanceRating;
        fillPerfScore.style.width = stats.performanceRating.includes('100') ? '100%' : '95%';

        valTimeMs.textContent = `${stats.timeMs} ms`;
        valPassesCount.textContent = `${stats.passesApplied.length} Passes Applied`;
        valRatio.textContent = stats.ratio;
        valBytesDiff.textContent = `${formatBytes(stats.originalSize)} → ${formatBytes(stats.obfuscatedSize)}`;

        statusBadge.innerHTML = '<span class="status-dot" style="background:var(--accent-emerald);"></span><span>Protected & Verified</span>';
        showToast('Obfuscation completed successfully!');
      } else {
        throw new Error(data.error || 'Failed to obfuscate');
      }
    } catch (err) {
      console.error(err);
      statusBadge.innerHTML = '<span class="status-dot" style="background:var(--accent-magenta);"></span><span>Error</span>';
      showToast(`Obfuscation Error: ${err.message}`, true);
    } finally {
      btnObfuscate.style.opacity = '1';
      btnObfuscate.style.pointerEvents = 'auto';
    }
  }

  btnObfuscate.addEventListener('click', performObfuscation);

  // Keyboard shortcut Ctrl+Enter or Cmd+Enter
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      performObfuscation();
    }
  });

  // AST Inspector
  btnAstInspector.addEventListener('click', () => {
    const code = sourceCodeInput.value.trim();
    if (!code) {
      showToast('Enter code first to inspect its AST', true);
      return;
    }

    try {
      // Create a simplified AST summary for display
      const summary = {
        meta: {
          engine: "O_bfuscate V2",
          author: "Undix",
          watermark: "protected by O_bfuscate v2, created by Undix",
          nativeNCG: optNative.checked
        },
        activePasses: [
          optNative.checked ? "Native NCG Directives (--!native, --!optimize 2)" : null,
          optStringCrypto.checked ? "Zero-Overhead Luau Buffer Cryptography" : null,
          optLocalizeGlobals.checked ? "Fastcall Upvalue Global Localization" : null,
          optIndirectMembers.checked ? "Member Expression Indirection" : null,
          optMangler.checked ? `Identifier Mangler (${selectManglerMode.value})` : null,
          optMba.checked ? "Mixed Boolean-Arithmetic (MBA)" : null,
          optCff.checked ? "Control Flow Flattening (CFF)" : null,
          optOpaque.checked ? "Invariant Opaque Predicates" : null,
          optAntiTamper.checked ? "Environment Anti-Tamper Guard" : null
        ].filter(Boolean),
        sourceMetrics: {
          lines: code.split('\n').length,
          bytes: new Blob([code]).size
        }
      };

      astJsonView.textContent = JSON.stringify(summary, null, 2);
      astModal.classList.add('open');
    } catch (err) {
      showToast(`AST Generation failed: ${err.message}`, true);
    }
  });

  modalCloseBtn.addEventListener('click', () => {
    astModal.classList.remove('open');
  });

  astModal.addEventListener('click', (e) => {
    if (e.target === astModal) {
      astModal.classList.remove('open');
    }
  });

  // Initial line numbers sync
  updateLineNumbers(sourceCodeInput, sourceLineNumbers, sourceStats);
  updateLineNumbers(outputCodeDisplay, outputLineNumbers, outputStats);
});
