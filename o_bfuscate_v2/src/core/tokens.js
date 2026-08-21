// src/core/tokens.js
// Token types and definitions for Luau / Lua syntax

const TokenType = {
  // Literals
  Number: 'Number',
  String: 'String',
  InterpolatedString: 'InterpolatedString',
  Boolean: 'Boolean',
  Nil: 'Nil',
  Identifier: 'Identifier',
  Vararg: 'Vararg', // ...

  // Keywords
  Keyword: 'Keyword',
  // and, break, do, else, elseif, end, false, for, function, if, in, local, nil, not, or, repeat, return, then, true, until, while, continue, type, export

  // Operators & Punctuation
  Operator: 'Operator',
  // + - * / // % ^ # == ~= <= >= < > = ( ) { } [ ] ; : , . .. ... += -= *= /= //= %= ^= ..= :: -> ?

  // Comments / Trivia
  Comment: 'Comment',
  Directive: 'Directive', // e.g. --!native, --!strict, --!optimize 2

  EOF: 'EOF'
};

const KEYWORDS = new Set([
  'and', 'break', 'do', 'else', 'elseif', 'end',
  'false', 'for', 'function', 'if', 'in', 'local',
  'nil', 'not', 'or', 'repeat', 'return', 'then',
  'true', 'until', 'while',
  // Luau statement keyword
  'continue'
]);

const COMPOUND_ASSIGNMENT_OPS = new Set([
  '+=', '-=', '*=', '/=', '//=', '%=', '^=', '..='
]);

const UNARY_OPS = new Set(['not', '#', '-', '~']);

const BINARY_OPS = new Set([
  '+', '-', '*', '/', '//', '%', '^', '..',
  '==', '~=', '<=', '>=', '<', '>',
  'and', 'or',
  // Luau bitwise (or 5.3)
  '&', '|', '~', '<<', '>>'
]);

module.exports = {
  TokenType,
  KEYWORDS,
  COMPOUND_ASSIGNMENT_OPS,
  UNARY_OPS,
  BINARY_OPS
};
