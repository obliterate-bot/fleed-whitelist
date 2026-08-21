// src/passes/mangler.js
// Identifier Mangler with Unicode Confusables, Barcodes, Hex-Hashes, and Scope Shadowing

const { ScopeAnalyzer } = require('../core/scope');
const { KEYWORDS } = require('../core/tokens');

// ASCII visual confusables & barcodes: 100% compliant with Roblox Luau ASCII lexer
const ASCII_CONFUSABLE_CHARS = ['l', 'I', '1', 'O', '0', 'i', '_'];

class IdentifierMangler {
  constructor(options = {}) {
    this.options = {
      mode: options.manglerMode || 'hex_hash', // 'confusables' | 'barcode' | 'hex_hash' | 'minified'
      prefix: options.prefix || '_0x',
      enableShadowing: options.enableShadowing !== false,
      ...options
    };
    this.counter = 0;
  }

  generateName(index, depth = 0) {
    switch (this.options.mode) {
      case 'confusables':
      case 'barcode': {
        let name = '';
        let n = index + 1;
        while (n > 0) {
          const rem = (n - 1) % ASCII_CONFUSABLE_CHARS.length;
          name += ASCII_CONFUSABLE_CHARS[rem];
          n = Math.floor((n - 1) / ASCII_CONFUSABLE_CHARS.length);
        }
        return `_${name}`;
      }

      case 'minified': {
        const letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_';
        let name = '';
        let n = index;
        do {
          name = letters[n % letters.length] + name;
          n = Math.floor(n / letters.length) - 1;
        } while (n >= 0);
        if (KEYWORDS.has(name)) {
          name = `_${name}`;
        }
        return name;
      }

      case 'hex_hash':
      default: {
        const hex = (index + 0x1000 + Math.imul(index, 0x5a3f)).toString(16).slice(-4);
        return `${this.options.prefix}${hex}`;
      }
    }
  }

  apply(ast) {
    const analyzer = new ScopeAnalyzer(ast);
    const { rootScope, allScopes } = analyzer.analyze();

    let globalCounter = 0;

    for (const scope of allScopes) {
      let localCounter = 0;
      for (const [originalName, symbol] of scope.declarations.entries()) {
        if (originalName === 'self') continue; // Preserve 'self' in methods

        const index = this.options.enableShadowing ? localCounter++ : globalCounter++;
        const mangled = this.generateName(index);

        symbol.mangledName = mangled;
        if (symbol.node) {
          symbol.node.mangledName = mangled;
        }
        for (const ref of symbol.references) {
          ref.mangledName = mangled;
        }
      }
    }

    return ast;
  }
}

module.exports = {
  IdentifierMangler
};
