// src/core/parser.js
// Recursive Descent Parser for Luau / Lua with full AST generation

const { TokenType, COMPOUND_ASSIGNMENT_OPS, UNARY_OPS } = require('./tokens');
const { Lexer } = require('./lexer');
const { NodeType, ASTNode } = require('./ast');

class Parser {
  constructor(input, options = {}) {
    this.lexer = new Lexer(input, options);
    this.tokens = this.lexer.tokenize();
    this.pos = 0;
    this.directives = this.lexer.directives;
    this.options = {
      stripTypes: options.stripTypes !== false,
      ...options
    };
  }

  peek(offset = 0) {
    const idx = this.pos + offset;
    return idx < this.tokens.length ? this.tokens[idx] : this.tokens[this.tokens.length - 1];
  }

  is(type, value = null) {
    const tok = this.peek();
    if (!tok || tok.type !== type) return false;
    if (value !== null && tok.value !== value) return false;
    return true;
  }

  consume(type = null, value = null) {
    const tok = this.peek();
    if (type && tok.type !== type) {
      throw new Error(`Expected token type ${type}, got ${tok.type} ('${tok.value}') at line ${tok.line}, col ${tok.column}`);
    }
    if (value && tok.value !== value) {
      throw new Error(`Expected '${value}', got '${tok.value}' at line ${tok.line}, col ${tok.column}`);
    }
    this.pos++;
    return tok;
  }

  match(type, value = null) {
    if (this.is(type, value)) {
      return this.consume();
    }
    return null;
  }

  parse() {
    const body = this.parseBlock();
    return new ASTNode(NodeType.Chunk, {
      body,
      directives: this.directives
    });
  }

  parseBlock() {
    const statements = [];
    while (!this.is(TokenType.EOF) && !this.isBlockEnd()) {
      // Semicolons
      if (this.match(TokenType.Operator, ';')) {
        continue;
      }
      const stmt = this.parseStatement();
      if (stmt) {
        statements.push(stmt);
      }
    }
    return statements;
  }

  isBlockEnd() {
    const tok = this.peek();
    if (tok.type === TokenType.Keyword) {
      return (
        tok.value === 'end' ||
        tok.value === 'else' ||
        tok.value === 'elseif' ||
        tok.value === 'until'
      );
    }
    return false;
  }

  // Parses optional type annotation e.g. `: number`, `: { [string]: any }`
  skipOptionalTypeAnnotation() {
    if (this.match(TokenType.Operator, ':')) {
      this.parseTypeSpecification();
      return true;
    }
    return false;
  }

  parseTypeSpecification() {
    let depth = 0;
    const STATEMENT_KEYWORDS = new Set([
      'local', 'function', 'if', 'while', 'do', 'repeat', 'for', 'return', 'break', 'continue',
      'then', 'end', 'else', 'elseif', 'until'
    ]);

    while (!this.is(TokenType.EOF)) {
      const tok = this.peek();

      if (tok.value === '(' || tok.value === '{' || tok.value === '<' || tok.value === '[') {
        depth++;
        this.consume();
      } else if (tok.value === ')' || tok.value === '}' || tok.value === '>' || tok.value === ']') {
        if (depth > 0) {
          depth--;
          this.consume();
        } else {
          // At depth 0, closing bracket belongs to outer construct (e.g. param list ')')
          break;
        }
      } else if (depth === 0) {
        if (
          tok.value === ',' || tok.value === '=' || tok.value === ';' ||
          (tok.type === TokenType.Keyword && STATEMENT_KEYWORDS.has(tok.value))
        ) {
          break;
        }
        this.consume();
      } else {
        this.consume();
      }
    }
  }

  consumeIdentifierOrKeyword() {
    const tok = this.peek();
    if (tok.type === TokenType.Identifier || tok.type === TokenType.Keyword) {
      return this.consume();
    }
    throw new Error(`Expected identifier or keyword, got ${tok.type} ('${tok.value}') at line ${tok.line}, col ${tok.column}`);
  }

  parseStatement() {
    const tok = this.peek();

    // Luau contextual type declaration:
    // type Name = ... OR type Name<T> = ...
    // export type Name = ... OR export type Name<T> = ...
    if (
      (tok.type === TokenType.Identifier && tok.value === 'type' && this.peek(1).type === TokenType.Identifier && (this.peek(2).value === '=' || this.peek(2).value === '<')) ||
      (tok.type === TokenType.Identifier && tok.value === 'export' && this.peek(1).value === 'type')
    ) {
      return this.parseTypeDeclaration();
    }

    if (tok.type === TokenType.Keyword) {
      switch (tok.value) {
        case 'local':
          return this.parseLocal();
        case 'function':
          return this.parseFunctionDeclaration();
        case 'if':
          return this.parseIfStatement();
        case 'while':
          return this.parseWhileStatement();
        case 'do':
          return this.parseDoStatement();
        case 'repeat':
          return this.parseRepeatStatement();
        case 'for':
          return this.parseForStatement();
        case 'return':
          return this.parseReturnStatement();
        case 'break':
          this.consume();
          return new ASTNode(NodeType.BreakStatement);
        case 'continue': // Luau continue
          this.consume();
          return new ASTNode(NodeType.ContinueStatement);
      }
    }

    // Call or Assignment statement
    return this.parseAssignmentOrCallStatement();
  }

  parseTypeDeclaration() {
    const isExport = this.match(TokenType.Keyword, 'export') !== null;
    this.consume(TokenType.Keyword, 'type');
    const name = this.consume(TokenType.Identifier).value;

    // Optional generics: <T, U>
    if (this.match(TokenType.Operator, '<')) {
      let gDepth = 1;
      while (!this.is(TokenType.EOF) && gDepth > 0) {
        if (this.is(TokenType.Operator, '<')) gDepth++;
        if (this.is(TokenType.Operator, '>')) gDepth--;
        this.consume();
      }
    }

    this.consume(TokenType.Operator, '=');
    this.parseTypeSpecification();

    return new ASTNode(NodeType.TypeAliasStatement, {
      name,
      isExport
    });
  }

  parseLocal() {
    this.consume(TokenType.Keyword, 'local');
    if (this.is(TokenType.Keyword, 'function')) {
      return this.parseLocalFunction();
    }

    const variables = [];
    while (true) {
      const idTok = this.consume(TokenType.Identifier);
      const ident = new ASTNode(NodeType.Identifier, { name: idTok.value });
      this.skipOptionalTypeAnnotation();
      variables.push(ident);
      if (!this.match(TokenType.Operator, ',')) break;
    }

    const init = [];
    if (this.match(TokenType.Operator, '=')) {
      while (true) {
        init.push(this.parseExpression());
        if (!this.match(TokenType.Operator, ',')) break;
      }
    }

    return new ASTNode(NodeType.LocalStatement, {
      variables,
      init
    });
  }

  parseLocalFunction() {
    this.consume(TokenType.Keyword, 'function');
    const idTok = this.consume(TokenType.Identifier);
    const identifier = new ASTNode(NodeType.Identifier, { name: idTok.value });

    // Optional generics <T>
    if (this.match(TokenType.Operator, '<')) {
      while (!this.match(TokenType.Operator, '>') && !this.is(TokenType.EOF)) {
        this.consume();
      }
    }

    this.consume(TokenType.Operator, '(');
    const params = this.parseParameterList();
    this.consume(TokenType.Operator, ')');

    this.skipOptionalTypeAnnotation(); // Return type
    const body = this.parseBlock();
    this.consume(TokenType.Keyword, 'end');

    return new ASTNode(NodeType.LocalFunctionDeclaration, {
      identifier,
      parameters: params.parameters,
      isVararg: params.isVararg,
      body
    });
  }

  parseFunctionDeclaration() {
    this.consume(TokenType.Keyword, 'function');

    // Function name: a.b.c:d
    let base = new ASTNode(NodeType.Identifier, { name: this.consume(TokenType.Identifier).value });
    let isMethod = false;

    while (this.match(TokenType.Operator, '.')) {
      const field = new ASTNode(NodeType.Identifier, { name: this.consumeIdentifierOrKeyword().value });
      base = new ASTNode(NodeType.MemberExpression, {
        base,
        identifier: field,
        indexer: '.'
      });
    }

    if (this.match(TokenType.Operator, ':')) {
      const field = new ASTNode(NodeType.Identifier, { name: this.consumeIdentifierOrKeyword().value });
      base = new ASTNode(NodeType.MemberExpression, {
        base,
        identifier: field,
        indexer: ':'
      });
      isMethod = true;
    }

    // Optional generics <T>
    if (this.match(TokenType.Operator, '<')) {
      while (!this.match(TokenType.Operator, '>') && !this.is(TokenType.EOF)) {
        this.consume();
      }
    }

    this.consume(TokenType.Operator, '(');
    const params = this.parseParameterList();
    this.consume(TokenType.Operator, ')');

    this.skipOptionalTypeAnnotation();
    const body = this.parseBlock();
    this.consume(TokenType.Keyword, 'end');

    return new ASTNode(NodeType.FunctionDeclaration, {
      identifier: base,
      parameters: params.parameters,
      isVararg: params.isVararg,
      isMethod,
      body
    });
  }

  parseParameterList() {
    const parameters = [];
    let isVararg = false;

    while (!this.is(TokenType.Operator, ')') && !this.is(TokenType.EOF)) {
      if (this.match(TokenType.Vararg, '...')) {
        isVararg = true;
        this.skipOptionalTypeAnnotation();
        break;
      }

      const idTok = this.consume(TokenType.Identifier);
      const ident = new ASTNode(NodeType.Identifier, { name: idTok.value });
      this.skipOptionalTypeAnnotation();
      parameters.push(ident);

      if (!this.match(TokenType.Operator, ',')) break;
    }

    return { parameters, isVararg };
  }

  parseIfStatement() {
    this.consume(TokenType.Keyword, 'if');
    const clauses = [];

    const condition = this.parseExpression();
    this.consume(TokenType.Keyword, 'then');
    const body = this.parseBlock();
    clauses.push({ condition, body });

    while (this.match(TokenType.Keyword, 'elseif')) {
      const elseifCond = this.parseExpression();
      this.consume(TokenType.Keyword, 'then');
      const elseifBody = this.parseBlock();
      clauses.push({ condition: elseifCond, body: elseifBody });
    }

    let elseBody = null;
    if (this.match(TokenType.Keyword, 'else')) {
      elseBody = this.parseBlock();
    }

    this.consume(TokenType.Keyword, 'end');

    return new ASTNode(NodeType.IfStatement, {
      clauses,
      elseBody
    });
  }

  parseWhileStatement() {
    this.consume(TokenType.Keyword, 'while');
    const condition = this.parseExpression();
    this.consume(TokenType.Keyword, 'do');
    const body = this.parseBlock();
    this.consume(TokenType.Keyword, 'end');

    return new ASTNode(NodeType.WhileStatement, {
      condition,
      body
    });
  }

  parseDoStatement() {
    this.consume(TokenType.Keyword, 'do');
    const body = this.parseBlock();
    this.consume(TokenType.Keyword, 'end');

    return new ASTNode(NodeType.DoStatement, { body });
  }

  parseRepeatStatement() {
    this.consume(TokenType.Keyword, 'repeat');
    const body = this.parseBlock();
    this.consume(TokenType.Keyword, 'until');
    const condition = this.parseExpression();

    return new ASTNode(NodeType.RepeatStatement, {
      condition,
      body
    });
  }

  parseForStatement() {
    this.consume(TokenType.Keyword, 'for');
    const idTok = this.consume(TokenType.Identifier);
    const variable = new ASTNode(NodeType.Identifier, { name: idTok.value });
    this.skipOptionalTypeAnnotation();

    // Numeric for: for i = start, end [, step] do
    if (this.match(TokenType.Operator, '=')) {
      const start = this.parseExpression();
      this.consume(TokenType.Operator, ',');
      const end = this.parseExpression();
      let step = null;
      if (this.match(TokenType.Operator, ',')) {
        step = this.parseExpression();
      }
      this.consume(TokenType.Keyword, 'do');
      const body = this.parseBlock();
      this.consume(TokenType.Keyword, 'end');

      return new ASTNode(NodeType.ForNumericStatement, {
        variable,
        start,
        end,
        step,
        body
      });
    }

    // Generic for: for a, b in iter, state, var do
    const variables = [variable];
    while (this.match(TokenType.Operator, ',')) {
      const nextId = this.consume(TokenType.Identifier);
      const nextIdent = new ASTNode(NodeType.Identifier, { name: nextId.value });
      this.skipOptionalTypeAnnotation();
      variables.push(nextIdent);
    }

    this.consume(TokenType.Keyword, 'in');
    const iterators = [];
    while (true) {
      iterators.push(this.parseExpression());
      if (!this.match(TokenType.Operator, ',')) break;
    }

    this.consume(TokenType.Keyword, 'do');
    const body = this.parseBlock();
    this.consume(TokenType.Keyword, 'end');

    return new ASTNode(NodeType.ForGenericStatement, {
      variables,
      iterators,
      body
    });
  }

  parseReturnStatement() {
    this.consume(TokenType.Keyword, 'return');
    const args = [];
    if (!this.isBlockEnd() && !this.is(TokenType.EOF) && !this.is(TokenType.Operator, ';')) {
      while (true) {
        args.push(this.parseExpression());
        if (!this.match(TokenType.Operator, ',')) break;
      }
    }
    this.match(TokenType.Operator, ';');

    return new ASTNode(NodeType.ReturnStatement, {
      arguments: args
    });
  }

  parseAssignmentOrCallStatement() {
    const expr = this.parsePrefixExpression();

    // Check for Luau compound assignment: a += b
    const nextTok = this.peek();
    if (nextTok && nextTok.type === TokenType.Operator && COMPOUND_ASSIGNMENT_OPS.has(nextTok.value)) {
      const op = this.consume().value;
      const right = this.parseExpression();
      return new ASTNode(NodeType.CompoundAssignmentStatement, {
        operator: op,
        variable: expr,
        value: right
      });
    }

    // Regular assignment: a, b = 1, 2
    if (this.is(TokenType.Operator, '=') || this.is(TokenType.Operator, ',')) {
      const variables = [expr];
      while (this.match(TokenType.Operator, ',')) {
        variables.push(this.parsePrefixExpression());
      }
      this.consume(TokenType.Operator, '=');
      const init = [];
      while (true) {
        init.push(this.parseExpression());
        if (!this.match(TokenType.Operator, ',')) break;
      }
      return new ASTNode(NodeType.AssignmentStatement, {
        variables,
        init
      });
    }

    // Call Statement
    if (
      expr.type === NodeType.CallExpression ||
      expr.type === NodeType.TableCallExpression ||
      expr.type === NodeType.StringCallExpression
    ) {
      return new ASTNode(NodeType.CallStatement, { expression: expr });
    }

    throw new Error(`Unexpected statement expression at line ${this.peek().line}`);
  }

  // Expressions & Precedence Climbing
  parseExpression() {
    // Luau if-expression: if cond then expr1 else expr2
    if (this.is(TokenType.Keyword, 'if')) {
      return this.parseIfExpression();
    }
    return this.parseBinaryExpression(0);
  }

  parseIfExpression() {
    this.consume(TokenType.Keyword, 'if');
    const condition = this.parseExpression();
    this.consume(TokenType.Keyword, 'then');
    const trueExpr = this.parseExpression();

    const elseifs = [];
    while (this.match(TokenType.Keyword, 'elseif')) {
      const c = this.parseExpression();
      this.consume(TokenType.Keyword, 'then');
      const e = this.parseExpression();
      elseifs.push({ condition: c, expression: e });
    }

    this.consume(TokenType.Keyword, 'else');
    const falseExpr = this.parseExpression();

    return new ASTNode(NodeType.IfExpression, {
      condition,
      trueExpression: trueExpr,
      elseifs,
      falseExpression: falseExpr
    });
  }

  getPrecedence(op) {
    switch (op) {
      case 'or': return 1;
      case 'and': return 2;
      case '<': case '>': case '<=': case '>=': case '~=': case '==': return 3;
      case '|': return 4;
      case '~': return 5;
      case '&': return 6;
      case '<<': case '>>': return 7;
      case '..': return 8;
      case '+': case '-': return 9;
      case '*': case '/': case '//': case '%': return 10;
      default: return 0;
    }
  }

  parseBinaryExpression(minPrecedence) {
    let left = this.parseUnaryExpression();

    while (true) {
      const tok = this.peek();
      if (!tok || (tok.type !== TokenType.Operator && tok.type !== TokenType.Keyword)) break;

      // Handle Luau type assertion `x :: any`
      if (tok.type === TokenType.Operator && tok.value === '::') {
        this.consume();
        this.parseTypeSpecification();
        continue;
      }

      const op = tok.value;
      const prec = this.getPrecedence(op);
      if (prec === 0 || prec < minPrecedence) break;

      this.consume();
      const isRightAssoc = op === '..' || op === '^';
      const nextMinPrec = isRightAssoc ? prec : prec + 1;
      const right = this.parseBinaryExpression(nextMinPrec);

      const isLogical = op === 'and' || op === 'or';
      left = new ASTNode(isLogical ? NodeType.LogicalExpression : NodeType.BinaryExpression, {
        operator: op,
        left,
        right
      });
    }

    return left;
  }

  parseUnaryExpression() {
    const tok = this.peek();
    if (tok && (
      (tok.type === TokenType.Operator && UNARY_OPS.has(tok.value)) ||
      (tok.type === TokenType.Keyword && tok.value === 'not')
    )) {
      this.consume();
      const argument = this.parseUnaryExpression();
      return new ASTNode(NodeType.UnaryExpression, {
        operator: tok.value,
        argument
      });
    }
    return this.parsePowerExpression();
  }

  parsePowerExpression() {
    let left = this.parsePrimaryExpression();
    if (this.match(TokenType.Operator, '^')) {
      const right = this.parseUnaryExpression();
      return new ASTNode(NodeType.BinaryExpression, {
        operator: '^',
        left,
        right
      });
    }
    return left;
  }

  parsePrimaryExpression() {
    const tok = this.peek();

    if (tok.type === TokenType.Nil) {
      this.consume();
      return new ASTNode(NodeType.NilLiteral, { value: null, raw: 'nil' });
    }
    if (tok.type === TokenType.Boolean) {
      this.consume();
      return new ASTNode(NodeType.BooleanLiteral, { value: tok.value, raw: String(tok.value) });
    }
    if (tok.type === TokenType.Number) {
      this.consume();
      return new ASTNode(NodeType.NumericLiteral, { value: tok.value, raw: tok.raw });
    }
    if (tok.type === TokenType.String) {
      this.consume();
      return new ASTNode(NodeType.StringLiteral, { value: tok.value, raw: tok.raw });
    }
    if (tok.type === TokenType.InterpolatedString) {
      this.consume();
      return new ASTNode(NodeType.InterpolatedStringExpression, { segments: tok.value, raw: tok.raw });
    }
    if (tok.type === TokenType.Vararg) {
      this.consume();
      return new ASTNode(NodeType.VarargLiteral, { value: '...', raw: '...' });
    }
    if (tok.type === TokenType.Keyword && tok.value === 'function') {
      return this.parseFunctionExpression();
    }
    if (this.is(TokenType.Operator, '{')) {
      return this.parseTableConstructor();
    }

    return this.parsePrefixExpression();
  }

  parsePrefixExpression() {
    let base = null;
    const tok = this.peek();

    if (this.match(TokenType.Operator, '(')) {
      base = this.parseExpression();
      this.consume(TokenType.Operator, ')');
    } else if (tok.type === TokenType.Identifier) {
      base = new ASTNode(NodeType.Identifier, { name: this.consume().value });
    } else {
      throw new Error(`Unexpected token '${tok.value}' in prefix expression at line ${tok.line}, col ${tok.column}`);
    }

    while (true) {
      // Member .field
      if (this.match(TokenType.Operator, '.')) {
        const idTok = this.consumeIdentifierOrKeyword();
        base = new ASTNode(NodeType.MemberExpression, {
          base,
          identifier: new ASTNode(NodeType.Identifier, { name: idTok.value }),
          indexer: '.'
        });
      }
      // Index [expr]
      else if (this.match(TokenType.Operator, '[')) {
        const index = this.parseExpression();
        this.consume(TokenType.Operator, ']');
        base = new ASTNode(NodeType.IndexExpression, {
          base,
          index
        });
      }
      // Method Call :method(...)
      else if (this.match(TokenType.Operator, ':')) {
        const methodTok = this.consumeIdentifierOrKeyword();
        const methodIdent = new ASTNode(NodeType.Identifier, { name: methodTok.value });
        const args = this.parseCallArguments();
        base = new ASTNode(NodeType.CallExpression, {
          base: new ASTNode(NodeType.MemberExpression, {
            base,
            identifier: methodIdent,
            indexer: ':'
          }),
          arguments: args
        });
      }
      // Direct Call (...)
      else if (this.is(TokenType.Operator, '(') || this.is(TokenType.Operator, '{') || this.is(TokenType.String)) {
        const args = this.parseCallArguments();
        base = new ASTNode(NodeType.CallExpression, {
          base,
          arguments: args
        });
      }
      // Luau type assertion :: type
      else if (this.match(TokenType.Operator, '::')) {
        this.parseTypeSpecification();
      }
      else {
        break;
      }
    }

    return base;
  }

  parseCallArguments() {
    if (this.match(TokenType.Operator, '(')) {
      const args = [];
      if (!this.match(TokenType.Operator, ')')) {
        while (true) {
          args.push(this.parseExpression());
          if (!this.match(TokenType.Operator, ',')) break;
        }
        this.consume(TokenType.Operator, ')');
      }
      return args;
    }

    if (this.is(TokenType.Operator, '{')) {
      return [this.parseTableConstructor()];
    }

    if (this.is(TokenType.String)) {
      const tok = this.consume();
      return [new ASTNode(NodeType.StringLiteral, { value: tok.value, raw: tok.raw })];
    }

    throw new Error(`Unexpected token in function call arguments at line ${this.peek().line}`);
  }

  parseFunctionExpression() {
    this.consume(TokenType.Keyword, 'function');

    // Optional generics <T>
    if (this.match(TokenType.Operator, '<')) {
      while (!this.match(TokenType.Operator, '>') && !this.is(TokenType.EOF)) {
        this.consume();
      }
    }

    this.consume(TokenType.Operator, '(');
    const params = this.parseParameterList();
    this.consume(TokenType.Operator, ')');

    this.skipOptionalTypeAnnotation();
    const body = this.parseBlock();
    this.consume(TokenType.Keyword, 'end');

    return new ASTNode(NodeType.FunctionExpression, {
      parameters: params.parameters,
      isVararg: params.isVararg,
      body
    });
  }

  parseTableConstructor() {
    this.consume(TokenType.Operator, '{');
    const fields = [];

    while (!this.match(TokenType.Operator, '}') && !this.is(TokenType.EOF)) {
      // [key] = val
      if (this.match(TokenType.Operator, '[')) {
        const key = this.parseExpression();
        this.consume(TokenType.Operator, ']');
        this.consume(TokenType.Operator, '=');
        const value = this.parseExpression();
        fields.push(new ASTNode(NodeType.TableKey, { key, value }));
      }
      // key = val (when peek is Identifier or Keyword followed by '=')
      else if ((this.is(TokenType.Identifier) || this.is(TokenType.Keyword)) && this.peek(1).value === '=') {
        const idTok = this.consume();
        this.consume(TokenType.Operator, '=');
        const value = this.parseExpression();
        fields.push(new ASTNode(NodeType.TableKeyString, {
          key: new ASTNode(NodeType.Identifier, { name: idTok.value }),
          value
        }));
      }
      // Array element
      else {
        const value = this.parseExpression();
        fields.push(new ASTNode(NodeType.TableValue, { value }));
      }

      if (!this.match(TokenType.Operator, ',') && !this.match(TokenType.Operator, ';')) {
        this.consume(TokenType.Operator, '}');
        break;
      }
    }

    return new ASTNode(NodeType.TableConstructorExpression, { fields });
  }
}

module.exports = {
  Parser
};
