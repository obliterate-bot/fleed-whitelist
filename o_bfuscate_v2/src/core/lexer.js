// src/core/lexer.js
// Industrial-Strength Lexer for Luau / Lua source code

const { TokenType, KEYWORDS, COMPOUND_ASSIGNMENT_OPS } = require('./tokens');

class Token {
  constructor(type, value, line, column, raw) {
    this.type = type;
    this.value = value;
    this.line = line;
    this.column = column;
    this.raw = raw !== undefined ? raw : String(value);
  }
}

class Lexer {
  constructor(input, options = {}) {
    this.input = input;
    this.length = input.length;
    this.pos = 0;
    this.line = 1;
    this.column = 1;
    this.options = {
      keepComments: options.keepComments || false,
      ...options
    };
    this.directives = [];
    this.tokens = [];
  }

  peek(offset = 0) {
    const idx = this.pos + offset;
    return idx < this.length ? this.input[idx] : null;
  }

  next() {
    if (this.pos >= this.length) return null;
    const char = this.input[this.pos++];
    if (char === '\n') {
      this.line++;
      this.column = 1;
    } else {
      this.column++;
    }
    return char;
  }

  isEOF() {
    return this.pos >= this.length;
  }

  isWhitespace(char) {
    return char === ' ' || char === '\t' || char === '\r' || char === '\n' || char === '\v' || char === '\f';
  }

  isDigit(char) {
    return char >= '0' && char <= '9';
  }

  isHexDigit(char) {
    return (
      (char >= '0' && char <= '9') ||
      (char >= 'a' && char <= 'f') ||
      (char >= 'A' && char <= 'F')
    );
  }

  isAlpha(char) {
    return (
      (char >= 'a' && char <= 'z') ||
      (char >= 'A' && char <= 'Z') ||
      char === '_' ||
      char.charCodeAt(0) >= 128 // Support unicode characters in identifiers
    );
  }

  isAlphaNumeric(char) {
    return this.isAlpha(char) || this.isDigit(char);
  }

  skipWhitespace() {
    while (!this.isEOF() && this.isWhitespace(this.peek())) {
      this.next();
    }
  }

  tokenize() {
    while (!this.isEOF()) {
      this.skipWhitespace();
      if (this.isEOF()) break;

      const line = this.line;
      const col = this.column;
      const char = this.peek();

      // Comments & Directives
      if (char === '-' && this.peek(1) === '-') {
        const commentToken = this.readComment();
        if (commentToken) {
          if (commentToken.type === TokenType.Directive) {
            this.directives.push(commentToken.value);
          }
          if (this.options.keepComments) {
            this.tokens.push(commentToken);
          }
        }
        continue;
      }

      // Strings (Single, Double, or Luau Interpolated)
      if (char === '"' || char === "'") {
        this.tokens.push(this.readQuotedString(char));
        continue;
      }

      if (char === '`') {
        this.tokens.push(this.readInterpolatedString());
        continue;
      }

      // Long Strings or Bracket Comments
      if (char === '[' && (this.peek(1) === '[' || this.peek(1) === '=')) {
        const longStr = this.tryReadLongBracketString();
        if (longStr) {
          this.tokens.push(longStr);
          continue;
        }
      }

      // Numbers
      if (this.isDigit(char) || (char === '.' && this.isDigit(this.peek(1)))) {
        this.tokens.push(this.readNumber());
        continue;
      }

      // Identifiers & Keywords
      if (this.isAlpha(char)) {
        this.tokens.push(this.readIdentifierOrKeyword());
        continue;
      }

      // Multi-character and single-character Operators & Punctuation
      const op = this.readOperator();
      if (op) {
        this.tokens.push(op);
        continue;
      }

      throw new Error(`Unexpected character '${char}' at line ${line}, column ${col}`);
    }

    this.tokens.push(new Token(TokenType.EOF, '<EOF>', this.line, this.column, ''));
    return this.tokens;
  }

  readComment() {
    const line = this.line;
    const col = this.column;
    this.next(); // -
    this.next(); // -

    // Check for directive, e.g. --!native, --!strict, --!optimize 2
    if (this.peek() === '!') {
      let directive = '';
      while (!this.isEOF() && this.peek() !== '\n' && this.peek() !== '\r') {
        directive += this.next();
      }
      return new Token(TokenType.Directive, directive.trim(), line, col, `--${directive}`);
    }

    // Check for long comment --[[ ... ]] or --[===[ ... ]===]
    if (this.peek() === '[') {
      const longContent = this.tryReadLongBracketContent();
      if (longContent !== null) {
        return new Token(TokenType.Comment, longContent, line, col, `--${longContent}`);
      }
    }

    // Line comment
    let comment = '';
    while (!this.isEOF() && this.peek() !== '\n' && this.peek() !== '\r') {
      comment += this.next();
    }
    return new Token(TokenType.Comment, comment, line, col, `--${comment}`);
  }

  tryReadLongBracketContent() {
    const startPos = this.pos;
    const startLine = this.line;
    const startCol = this.column;

    if (this.peek() !== '[') return null;
    let equalsCount = 0;
    let i = 1;
    while (this.peek(i) === '=') {
      equalsCount++;
      i++;
    }

    if (this.peek(i) !== '[') {
      return null;
    }

    // Consume opening [===...[
    for (let k = 0; k <= i; k++) {
      this.next();
    }

    // Skip immediate newline if present
    if (this.peek() === '\r' && this.peek(1) === '\n') {
      this.next();
      this.next();
    } else if (this.peek() === '\n') {
      this.next();
    }

    let content = '';
    while (!this.isEOF()) {
      if (this.peek() === ']') {
        let closingEquals = 0;
        let j = 1;
        while (this.peek(j) === '=') {
          closingEquals++;
          j++;
        }
        if (closingEquals === equalsCount && this.peek(j) === ']') {
          // Consume closing ]===...]
          for (let k = 0; k <= j; k++) {
            this.next();
          }
          return content;
        }
      }
      content += this.next();
    }

    throw new Error(`Unfinished long bracket comment/string starting at line ${startLine}, col ${startCol}`);
  }

  tryReadLongBracketString() {
    const line = this.line;
    const col = this.column;
    const content = this.tryReadLongBracketContent();
    if (content !== null) {
      return new Token(TokenType.String, content, line, col, `[[${content}]]`);
    }
    return null;
  }

  readQuotedString(quote) {
    const line = this.line;
    const col = this.column;
    this.next(); // Consume opening quote

    let str = '';
    let raw = quote;

    while (!this.isEOF()) {
      const char = this.peek();
      if (char === quote) {
        this.next(); // Consume closing quote
        raw += quote;
        return new Token(TokenType.String, str, line, col, raw);
      }

      if (char === '\n' || char === '\r') {
        throw new Error(`Unfinished string at line ${line}, column ${col}`);
      }

      if (char === '\\') {
        raw += this.next(); // \
        const esc = this.next();
        raw += esc;

        if (esc === 'a') str += '\x07';
        else if (esc === 'b') str += '\b';
        else if (esc === 'f') str += '\f';
        else if (esc === 'n') str += '\n';
        else if (esc === 'r') str += '\r';
        else if (esc === 't') str += '\t';
        else if (esc === 'v') str += '\v';
        else if (esc === '\\') str += '\\';
        else if (esc === '"') str += '"';
        else if (esc === "'") str += "'";
        else if (esc === '\n' || esc === '\r') {
          str += '\n';
        } else if (esc === 'z') {
          // Skip whitespace
          while (!this.isEOF() && this.isWhitespace(this.peek())) {
            raw += this.next();
          }
        } else if (esc === 'x') {
          // Hex escape \xHH
          const h1 = this.next();
          const h2 = this.next();
          raw += h1 + h2;
          const code = parseInt(h1 + h2, 16);
          if (isNaN(code)) throw new Error(`Invalid hex escape \\x${h1}${h2} at line ${line}`);
          str += String.fromCharCode(code);
        } else if (esc === 'u') {
          // Unicode escape \u{HHHH}
          if (this.peek() === '{') {
            raw += this.next(); // {
            let hex = '';
            while (!this.isEOF() && this.peek() !== '}') {
              const h = this.next();
              raw += h;
              hex += h;
            }
            if (this.peek() === '}') raw += this.next();
            const code = parseInt(hex, 16);
            if (isNaN(code)) throw new Error(`Invalid unicode escape \\u{${hex}} at line ${line}`);
            str += String.fromCodePoint(code);
          } else {
            str += 'u';
          }
        } else if (this.isDigit(esc)) {
          // Decimal escape \ddd
          let dStr = esc;
          if (this.isDigit(this.peek())) {
            const d2 = this.next();
            raw += d2;
            dStr += d2;
            if (this.isDigit(this.peek())) {
              const d3 = this.next();
              raw += d3;
              dStr += d3;
            }
          }
          const code = parseInt(dStr, 10);
          str += String.fromCharCode(code);
        } else {
          str += esc;
        }
      } else {
        const c = this.next();
        raw += c;
        str += c;
      }
    }

    throw new Error(`Unfinished string at line ${line}, column ${col}`);
  }

  readInterpolatedString() {
    const line = this.line;
    const col = this.column;
    this.next(); // Consume `

    let raw = '`';
    let segments = []; // Array of string chunks and nested expressions
    let currentStr = '';

    while (!this.isEOF()) {
      const char = this.peek();
      if (char === '`') {
        this.next(); // Close backtick
        raw += '`';
        segments.push({ type: 'string', value: currentStr });
        return new Token(TokenType.InterpolatedString, segments, line, col, raw);
      }

      if (char === '{') {
        this.next(); // Consume {
        raw += '{';
        segments.push({ type: 'string', value: currentStr });
        currentStr = '';

        // Read expression inside {...}
        let exprStr = '';
        let braceDepth = 1;
        while (!this.isEOF() && braceDepth > 0) {
          const c = this.peek();
          if (c === '{') braceDepth++;
          else if (c === '}') {
            braceDepth--;
            if (braceDepth === 0) {
              this.next();
              raw += '}';
              break;
            }
          }
          const ch = this.next();
          exprStr += ch;
          raw += ch;
        }
        segments.push({ type: 'expr', value: exprStr });
      } else if (char === '\\') {
        raw += this.next();
        const esc = this.next();
        raw += esc;
        if (esc === '`') currentStr += '`';
        else if (esc === '{') currentStr += '{';
        else if (esc === 'n') currentStr += '\n';
        else if (esc === 't') currentStr += '\t';
        else if (esc === 'r') currentStr += '\r';
        else if (esc === '\\') currentStr += '\\';
        else currentStr += '\\' + esc;
      } else {
        const c = this.next();
        raw += c;
        currentStr += c;
      }
    }

    throw new Error(`Unfinished interpolated string starting at line ${line}, col ${col}`);
  }

  readNumber() {
    const line = this.line;
    const col = this.column;
    let numStr = '';

    // Hex: 0x... or 0X...
    if (this.peek() === '0' && (this.peek(1) === 'x' || this.peek(1) === 'X')) {
      numStr += this.next(); // 0
      numStr += this.next(); // x
      while (!this.isEOF() && (this.isHexDigit(this.peek()) || this.peek() === '_')) {
        const c = this.next();
        if (c !== '_') numStr += c;
      }
      // Hex float support e.g. 0x1.5p3
      if (this.peek() === '.') {
        numStr += this.next();
        while (!this.isEOF() && (this.isHexDigit(this.peek()) || this.peek() === '_')) {
          const c = this.next();
          if (c !== '_') numStr += c;
        }
      }
      if (this.peek() === 'p' || this.peek() === 'P') {
        numStr += this.next();
        if (this.peek() === '+' || this.peek() === '-') {
          numStr += this.next();
        }
        while (!this.isEOF() && this.isDigit(this.peek())) {
          numStr += this.next();
        }
      }
      return new Token(TokenType.Number, Number(numStr), line, col, numStr);
    }

    // Binary: 0b... or 0B... (Luau extension)
    if (this.peek() === '0' && (this.peek(1) === 'b' || this.peek(1) === 'B')) {
      numStr += this.next(); // 0
      numStr += this.next(); // b
      let binDigits = '';
      while (!this.isEOF() && (this.peek() === '0' || this.peek() === '1' || this.peek() === '_')) {
        const c = this.next();
        if (c !== '_') {
          numStr += c;
          binDigits += c;
        }
      }
      const val = parseInt(binDigits, 2);
      return new Token(TokenType.Number, val, line, col, numStr);
    }

    // Decimal with optional fraction and exponent
    while (!this.isEOF() && (this.isDigit(this.peek()) || this.peek() === '_')) {
      const c = this.next();
      if (c !== '_') numStr += c;
    }

    if (this.peek() === '.' && this.isDigit(this.peek(1))) {
      numStr += this.next(); // .
      while (!this.isEOF() && (this.isDigit(this.peek()) || this.peek() === '_')) {
        const c = this.next();
        if (c !== '_') numStr += c;
      }
    }

    if (this.peek() === 'e' || this.peek() === 'E') {
      numStr += this.next();
      if (this.peek() === '+' || this.peek() === '-') {
        numStr += this.next();
      }
      while (!this.isEOF() && (this.isDigit(this.peek()) || this.peek() === '_')) {
        const c = this.next();
        if (c !== '_') numStr += c;
      }
    }

    const val = parseFloat(numStr);
    return new Token(TokenType.Number, val, line, col, numStr);
  }

  readIdentifierOrKeyword() {
    const line = this.line;
    const col = this.column;
    let ident = '';

    while (!this.isEOF() && this.isAlphaNumeric(this.peek())) {
      ident += this.next();
    }

    if (KEYWORDS.has(ident)) {
      if (ident === 'true') {
        return new Token(TokenType.Boolean, true, line, col, ident);
      }
      if (ident === 'false') {
        return new Token(TokenType.Boolean, false, line, col, ident);
      }
      if (ident === 'nil') {
        return new Token(TokenType.Nil, null, line, col, ident);
      }
      return new Token(TokenType.Keyword, ident, line, col, ident);
    }

    return new Token(TokenType.Identifier, ident, line, col, ident);
  }

  readOperator() {
    const line = this.line;
    const col = this.column;
    const c1 = this.peek();
    const c2 = this.peek(1);
    const c3 = this.peek(2);

    // 3-character operators
    if (c1 === '.' && c2 === '.' && c3 === '.') {
      this.next(); this.next(); this.next();
      return new Token(TokenType.Vararg, '...', line, col, '...');
    }
    if (c1 === '.' && c2 === '.' && c3 === '=') {
      this.next(); this.next(); this.next();
      return new Token(TokenType.Operator, '..=', line, col, '..=');
    }
    if (c1 === '/' && c2 === '/' && c3 === '=') {
      this.next(); this.next(); this.next();
      return new Token(TokenType.Operator, '//=', line, col, '//=');
    }

    // 2-character operators
    const twoChars = c1 + c2;
    if (
      twoChars === '==' || twoChars === '~=' || twoChars === '<=' || twoChars === '>=' ||
      twoChars === '..' || twoChars === '+=' || twoChars === '-=' || twoChars === '*=' ||
      twoChars === '/=' || twoChars === '%=' || twoChars === '^=' || twoChars === '//' ||
      twoChars === '::' || twoChars === '->' || twoChars === '<<' || twoChars === '>>'
    ) {
      this.next(); this.next();
      return new Token(TokenType.Operator, twoChars, line, col, twoChars);
    }

    // 1-character operators and punctuation
    if (
      c1 === '+' || c1 === '-' || c1 === '*' || c1 === '/' || c1 === '%' || c1 === '^' ||
      c1 === '#' || c1 === '=' || c1 === '<' || c1 === '>' || c1 === '(' || c1 === ')' ||
      c1 === '{' || c1 === '}' || c1 === '[' || c1 === ']' || c1 === ';' || c1 === ':' ||
      c1 === ',' || c1 === '.' || c1 === '&' || c1 === '|' || c1 === '~' || c1 === '?'
    ) {
      this.next();
      return new Token(TokenType.Operator, c1, line, col, c1);
    }

    return null;
  }
}

module.exports = {
  Token,
  Lexer
};
