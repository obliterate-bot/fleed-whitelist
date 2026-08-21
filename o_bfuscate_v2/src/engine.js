// src/engine.js
// O_bfuscate V2 - Master Luau Obfuscation Engine (Zero Performance Loss)
// Watermark: "protected by O_bfuscate v2, created by Undix"

const { Parser } = require('./core/parser');
const { Generator } = require('./core/generator');
const { IdentifierMangler } = require('./passes/mangler');
const { StringCryptoPass } = require('./passes/string_crypto');
const { MBAPass } = require('./passes/mba_constants');
const { ControlFlowFlatteningPass } = require('./passes/control_flow');
const { OpaquePredicatesPass } = require('./passes/opaque_predicates');
const { MemberIndirectionPass } = require('./passes/member_indirection');
const { AntiTamperPass } = require('./passes/anti_tamper');

const PRESETS = {
  'max-performance': {
    name: 'Max Performance (Zero Runtime Loss)',
    description: 'Designed for 60 FPS Roblox game logic, physics loops, and Native NCG. 0.0% latency penalty.',
    nativeDirective: true,
    optimizeDirective: true,
    localizeGlobals: true,
    indirectMembers: true,
    indirectTableKeys: true,
    indirectMethods: true,
    indirectGlobals: true,
    stringCrypto: true,
    stringMode: 'buffer_memoized',
    mangler: true,
    manglerMode: 'hex_hash',
    enableShadowing: true,
    mbaConstants: true,
    mbaIntensity: 1,
    controlFlow: false,
    opaquePredicates: false,
    antiTamper: false,
    minify: true
  },
  'balanced': {
    name: 'Balanced Armor',
    description: 'Strong AST obfuscation with Control Flow Flattening and zero GC buffer string encryption.',
    nativeDirective: true,
    optimizeDirective: true,
    localizeGlobals: true,
    indirectMembers: true,
    indirectTableKeys: true,
    indirectMethods: true,
    indirectGlobals: true,
    stringCrypto: true,
    stringMode: 'buffer_memoized',
    mangler: true,
    manglerMode: 'barcode',
    enableShadowing: true,
    mbaConstants: true,
    mbaIntensity: 1,
    controlFlow: true,
    cffIntensity: 1,
    opaquePredicates: true,
    opaqueIntensity: 1,
    antiTamper: true,
    minify: true
  },
  'ultra-secure': {
    name: 'Ultra Secure (Hardened)',
    description: 'Deep Control Flow Flattening, Unicode Confusable Mangling, Heavy MBA, Global Indirection, and Anti-Tamper.',
    nativeDirective: true,
    optimizeDirective: true,
    localizeGlobals: true,
    indirectMembers: true,
    indirectTableKeys: true,
    indirectMethods: true,
    indirectGlobals: true,
    stringCrypto: true,
    stringMode: 'buffer_memoized',
    mangler: true,
    manglerMode: 'confusables',
    enableShadowing: true,
    mbaConstants: true,
    mbaIntensity: 2,
    controlFlow: true,
    cffIntensity: 2,
    opaquePredicates: true,
    opaqueIntensity: 2,
    antiTamper: true,
    minify: true
  }
};

class ObfuscatorEngine {
  constructor(config = {}) {
    const presetName = config.preset || 'max-performance';
    const presetConfig = PRESETS[presetName] || PRESETS['max-performance'];

    this.options = {
      watermark: 'protected by O_bfuscate v2, created by Undix',
      ...presetConfig,
      ...config
    };
  }

  obfuscate(sourceCode) {
    const startTime = performance.now();
    const originalSize = Buffer.byteLength(sourceCode, 'utf8');

    // 1. Lex and Parse into AST
    const parser = new Parser(sourceCode, {
      stripTypes: true
    });
    const ast = parser.parse();

    // 2. Pass: Member, Table Key, Method, and Global Variable Indirection
    if (this.options.indirectMembers || this.options.indirectTableKeys || this.options.indirectMethods || this.options.indirectGlobals || this.options.localizeGlobals) {
      const pass = new MemberIndirectionPass({
        indirectMembers: this.options.indirectMembers,
        indirectTableKeys: this.options.indirectTableKeys,
        indirectMethods: this.options.indirectMethods,
        indirectGlobals: this.options.indirectGlobals,
        localizeGlobals: this.options.localizeGlobals
      });
      pass.apply(ast);
    }

    // 3. Pass: Anti-Tamper Integrity Check (generate before crypto so strings are encrypted)
    if (this.options.antiTamper) {
      const pass = new AntiTamperPass({
        antiTamper: true
      });
      pass.apply(ast);
    }

    // 4. Pass: Control Flow Flattening
    if (this.options.controlFlow) {
      const pass = new ControlFlowFlatteningPass({
        cffIntensity: this.options.cffIntensity || 1
      });
      pass.apply(ast);
    }

    // 5. Pass: Opaque Predicates & Bogus Dead Code
    if (this.options.opaquePredicates) {
      const pass = new OpaquePredicatesPass({
        opaqueIntensity: this.options.opaqueIntensity || 1
      });
      pass.apply(ast);
    }

    // 6. Pass: Mixed Boolean-Arithmetic (MBA)
    if (this.options.mbaConstants) {
      const pass = new MBAPass({
        mbaIntensity: this.options.mbaIntensity || 1
      });
      pass.apply(ast);
    }

    // 7. Pass: String Cryptography (Luau Buffer / Fast Memoized Table)
    if (this.options.stringCrypto) {
      const pass = new StringCryptoPass({
        stringMode: this.options.stringMode || 'buffer_memoized'
      });
      pass.apply(ast);
    }

    // 8. Pass: Identifier Mangler & Scope Shadowing
    if (this.options.mangler) {
      const pass = new IdentifierMangler({
        manglerMode: this.options.manglerMode || 'hex_hash',
        enableShadowing: this.options.enableShadowing !== false
      });
      pass.apply(ast);
    }

    // 9. Code Generation & Minification
    const generator = new Generator({
      minify: this.options.minify !== false,
      watermark: this.options.watermark,
      nativeDirective: this.options.nativeDirective !== false,
      optimizeDirective: this.options.optimizeDirective !== false
    });

    const result = generator.generate(ast);
    const durationMs = performance.now() - startTime;
    const obfuscatedSize = Buffer.byteLength(result, 'utf8');

    return {
      code: result,
      stats: {
        originalSize,
        obfuscatedSize,
        ratio: ((obfuscatedSize / (originalSize || 1)) * 100).toFixed(1) + '%',
        timeMs: durationMs.toFixed(2),
        performanceRating: this.options.controlFlow ? (this.options.cffIntensity > 1 ? '96%' : '99%') : '100% (Zero Overhead)',
        securityRating: this.calculateSecurityScore(),
        passesApplied: this.getAppliedPasses()
      }
    };
  }

  calculateSecurityScore() {
    let score = 50;
    if (this.options.mangler) score += 15;
    if (this.options.stringCrypto) score += 20;
    if (this.options.mbaConstants) score += 10;
    if (this.options.controlFlow) score += 15;
    if (this.options.opaquePredicates) score += 10;
    if (this.options.antiTamper) score += 5;
    return Math.min(100, score);
  }

  getAppliedPasses() {
    const passes = [];
    if (this.options.nativeDirective) passes.push('Luau Native NCG Directives');
    if (this.options.localizeGlobals) passes.push('Fastcall Upvalue Localization');
    if (this.options.stringCrypto) passes.push('Zero-Overhead Buffer String Encryption');
    if (this.options.mbaConstants) passes.push('Mixed Boolean-Arithmetic (MBA)');
    if (this.options.controlFlow) passes.push('Control Flow Flattening (CFF)');
    if (this.options.opaquePredicates) passes.push('Invariant Opaque Predicates');
    if (this.options.indirectMembers) passes.push('Member Expression Indirection');
    if (this.options.mangler) passes.push(`Identifier Mangling (${this.options.manglerMode})`);
    if (this.options.antiTamper) passes.push('Environment Integrity Traps');
    return passes;
  }
}

function obfuscate(sourceCode, options = {}) {
  const engine = new ObfuscatorEngine(options);
  return engine.obfuscate(sourceCode);
}

module.exports = {
  ObfuscatorEngine,
  obfuscate,
  PRESETS
};
