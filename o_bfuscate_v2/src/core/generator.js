// src/core/generator.js
// Luau / Lua Code Generator & AST Serializer for O_bfuscate V2

const { NodeType } = require('./ast');

class Generator {
  constructor(options = {}) {
    this.options = {
      minify: options.minify !== false,
      watermark: options.watermark !== undefined ? options.watermark : 'protected by O_bfuscate v2, created by Undix',
      nativeDirective: options.nativeDirective !== false,
      optimizeDirective: options.optimizeDirective !== false,
      ...options
    };
    this.indent = 0;
  }

  generate(ast) {
    let code = '';

    // Directives
    if (this.options.nativeDirective) {
      code += '--!native\n';
    }
    if (this.options.optimizeDirective) {
      code += '--!optimize 2\n';
    }

    // Watermark
    if (this.options.watermark) {
      code += `-- [ ${this.options.watermark} ]\n`;
    }

    code += this.formatBlock(ast.body);
    return code.trim();
  }

  formatBlock(statements) {
    if (!statements || statements.length === 0) return '';
    const sep = this.options.minify ? ' ' : '\n';
    const lines = [];

    for (let i = 0; i < statements.length; i++) {
      const stmt = statements[i];
      const stmtCode = this.formatStatement(stmt);
      if (stmtCode) {
        lines.push(stmtCode);
      }
    }

    if (this.options.minify) {
      // Ensure statements don't merge into invalid syntax
      let result = '';
      for (let i = 0; i < lines.length; i++) {
        const cur = lines[i];
        if (result.length > 0) {
          const lastChar = result[result.length - 1];
          const firstChar = cur[0];
          if (
            (this.isAlphaNum(lastChar) && this.isAlphaNum(firstChar)) ||
            (lastChar === '(' && firstChar === '(') ||
            (lastChar === '-' && firstChar === '-')
          ) {
            result += ' ';
          } else {
            result += ' ';
          }
        }
        result += cur;
        if (result.endsWith(';') || result.endsWith('end')) {
          // clean
        }
      }
      return result;
    } else {
      return lines.map(line => '  '.repeat(this.indent) + line).join('\n');
    }
  }

  isAlphaNum(char) {
    if (!char) return false;
    const c = char.charCodeAt(0);
    return (
      (c >= 48 && c <= 57) || // 0-9
      (c >= 65 && c <= 90) || // A-Z
      (c >= 97 && c <= 122) || // a-z
      c === 95 || // _
      c >= 128 // Unicode
    );
  }

  formatStatement(node) {
    if (!node) return '';

    switch (node.type) {
      case NodeType.LocalStatement: {
        const vars = node.variables.map(v => this.formatExpression(v)).join(this.options.minify ? ',' : ', ');
        if (node.init && node.init.length > 0) {
          const inits = node.init.map(e => this.formatExpression(e)).join(this.options.minify ? ',' : ', ');
          return `local ${vars}=${inits}`;
        }
        return `local ${vars}`;
      }

      case NodeType.LocalFunctionDeclaration: {
        const name = this.formatExpression(node.identifier);
        const params = node.parameters.map(p => this.formatExpression(p));
        if (node.isVararg) params.push('...');
        const paramStr = params.join(this.options.minify ? ',' : ', ');
        const bodyStr = this.formatBlock(node.body);
        return `local function ${name}(${paramStr})${this.options.minify ? ' ' : '\n'}${bodyStr}${this.options.minify ? ' ' : '\n'}end`;
      }

      case NodeType.FunctionDeclaration: {
        const name = this.formatExpression(node.identifier);
        const params = node.parameters.map(p => this.formatExpression(p));
        if (node.isVararg) params.push('...');
        const paramStr = params.join(this.options.minify ? ',' : ', ');
        const bodyStr = this.formatBlock(node.body);
        return `function ${name}(${paramStr})${this.options.minify ? ' ' : '\n'}${bodyStr}${this.options.minify ? ' ' : '\n'}end`;
      }

      case NodeType.AssignmentStatement: {
        const vars = node.variables.map(v => this.formatExpression(v)).join(this.options.minify ? ',' : ', ');
        const inits = node.init.map(e => this.formatExpression(e)).join(this.options.minify ? ',' : ', ');
        return `${vars}=${inits}`;
      }

      case NodeType.CompoundAssignmentStatement: {
        const v = this.formatExpression(node.variable);
        const val = this.formatExpression(node.value);
        return `${v} ${node.operator} ${val}`;
      }

      case NodeType.CallStatement: {
        return this.formatExpression(node.expression);
      }

      case NodeType.IfStatement: {
        let code = '';
        for (let i = 0; i < node.clauses.length; i++) {
          const clause = node.clauses[i];
          const cond = this.formatExpression(clause.condition);
          const body = this.formatBlock(clause.body);
          if (i === 0) {
            code += `if ${cond} then${this.options.minify ? ' ' : '\n'}${body}`;
          } else {
            code += `${this.options.minify ? ' ' : '\n'}elseif ${cond} then${this.options.minify ? ' ' : '\n'}${body}`;
          }
        }
        if (node.elseBody) {
          const elseBody = this.formatBlock(node.elseBody);
          code += `${this.options.minify ? ' ' : '\n'}else${this.options.minify ? ' ' : '\n'}${elseBody}`;
        }
        code += `${this.options.minify ? ' ' : '\n'}end`;
        return code;
      }

      case NodeType.WhileStatement: {
        const cond = this.formatExpression(node.condition);
        const body = this.formatBlock(node.body);
        return `while ${cond} do${this.options.minify ? ' ' : '\n'}${body}${this.options.minify ? ' ' : '\n'}end`;
      }

      case NodeType.DoStatement: {
        const body = this.formatBlock(node.body);
        return `do${this.options.minify ? ' ' : '\n'}${body}${this.options.minify ? ' ' : '\n'}end`;
      }

      case NodeType.RepeatStatement: {
        const body = this.formatBlock(node.body);
        const cond = this.formatExpression(node.condition);
        return `repeat${this.options.minify ? ' ' : '\n'}${body}${this.options.minify ? ' ' : '\n'}until ${cond}`;
      }

      case NodeType.ForNumericStatement: {
        const v = this.formatExpression(node.variable);
        const start = this.formatExpression(node.start);
        const end = this.formatExpression(node.end);
        const step = node.step ? `,${this.formatExpression(node.step)}` : '';
        const body = this.formatBlock(node.body);
        return `for ${v}=${start},${end}${step} do${this.options.minify ? ' ' : '\n'}${body}${this.options.minify ? ' ' : '\n'}end`;
      }

      case NodeType.ForGenericStatement: {
        const vars = node.variables.map(v => this.formatExpression(v)).join(this.options.minify ? ',' : ', ');
        const iters = node.iterators.map(e => this.formatExpression(e)).join(this.options.minify ? ',' : ', ');
        const body = this.formatBlock(node.body);
        return `for ${vars} in ${iters} do${this.options.minify ? ' ' : '\n'}${body}${this.options.minify ? ' ' : '\n'}end`;
      }

      case NodeType.ReturnStatement: {
        if (!node.arguments || node.arguments.length === 0) {
          return 'return';
        }
        const args = node.arguments.map(a => this.formatExpression(a)).join(this.options.minify ? ',' : ', ');
        return `return ${args}`;
      }

      case NodeType.BreakStatement:
        return 'break';

      case NodeType.ContinueStatement:
        return 'continue';

      case NodeType.TypeAliasStatement:
        // Strip or export type
        return '';

      default:
        throw new Error(`Unknown statement type: ${node.type}`);
    }
  }

  getPrecedence(node) {
    if (!node) return 0;
    if (node.type === NodeType.LogicalExpression) {
      return node.operator === 'or' ? 1 : 2;
    }
    if (node.type === NodeType.BinaryExpression) {
      switch (node.operator) {
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
        case '^': return 12;
        default: return 0;
      }
    }
    if (node.type === NodeType.UnaryExpression) {
      return 11;
    }
    return 100;
  }

  formatExpression(node, parentPrec = 0) {
    if (!node) return '';

    let code = '';
    const myPrec = this.getPrecedence(node);

    switch (node.type) {
      case NodeType.Identifier:
        code = node.mangledName || node.name;
        break;

      case NodeType.NumericLiteral:
        code = String(node.value);
        break;

      case NodeType.StringLiteral: {
        const escaped = this.escapeString(node.value);
        code = `"${escaped}"`;
        break;
      }

      case NodeType.BooleanLiteral:
        code = node.value ? 'true' : 'false';
        break;

      case NodeType.NilLiteral:
        code = 'nil';
        break;

      case NodeType.VarargLiteral:
        code = '...';
        break;

      case NodeType.InterpolatedStringExpression: {
        let res = '`';
        for (const seg of node.segments) {
          if (seg.type === 'string') res += seg.value;
          else if (seg.type === 'expr') res += `{${seg.value}}`;
        }
        res += '`';
        code = res;
        break;
      }

      case NodeType.IfExpression: {
        const cond = this.formatExpression(node.condition);
        const tExpr = this.formatExpression(node.trueExpression);
        let middle = '';
        if (node.elseifs) {
          for (const elif of node.elseifs) {
            middle += ` elseif ${this.formatExpression(elif.condition)} then ${this.formatExpression(elif.expression)}`;
          }
        }
        const fExpr = this.formatExpression(node.falseExpression);
        code = `if ${cond} then ${tExpr}${middle} else ${fExpr}`;
        break;
      }

      case NodeType.BinaryExpression:
      case NodeType.LogicalExpression: {
        const leftCode = this.formatExpression(node.left, myPrec);
        const rightCode = this.formatExpression(node.right, node.operator === '^' || node.operator === '..' ? myPrec : myPrec + 1);
        const sep = this.options.minify ? (this.needsSpaceAroundOp(node.operator) ? ' ' : '') : ' ';
        code = `${leftCode}${sep}${node.operator}${sep}${rightCode}`;
        break;
      }

      case NodeType.UnaryExpression: {
        const argCode = this.formatExpression(node.argument, myPrec);
        const sep = (node.operator === 'not' || this.isAlphaNum(node.operator)) ? ' ' : '';
        code = `${node.operator}${sep}${argCode}`;
        break;
      }

      case NodeType.MemberExpression: {
        const baseCode = this.formatExpression(node.base, 100);
        const idCode = node.identifier.name;
        code = `${baseCode}${node.indexer}${idCode}`;
        break;
      }

      case NodeType.IndexExpression: {
        const baseCode = this.formatExpression(node.base, 100);
        const indexCode = this.formatExpression(node.index, 0);
        code = `${baseCode}[${indexCode}]`;
        break;
      }

      case NodeType.CallExpression: {
        const baseCode = this.formatExpression(node.base, 100);
        const argsCode = node.arguments.map(a => this.formatExpression(a, 0)).join(this.options.minify ? ',' : ', ');
        code = `${baseCode}(${argsCode})`;
        break;
      }

      case NodeType.FunctionExpression: {
        const params = node.parameters.map(p => this.formatExpression(p));
        if (node.isVararg) params.push('...');
        const paramStr = params.join(this.options.minify ? ',' : ', ');
        const bodyStr = this.formatBlock(node.body);
        code = `function(${paramStr})${this.options.minify ? ' ' : '\n'}${bodyStr}${this.options.minify ? ' ' : '\n'}end`;
        break;
      }

      case NodeType.TableConstructorExpression: {
        const fieldStrs = [];
        for (const field of node.fields) {
          if (field.type === NodeType.TableKey) {
            const k = this.formatExpression(field.key, 0);
            const v = this.formatExpression(field.value, 0);
            fieldStrs.push(`[${k}]=${v}`);
          } else if (field.type === NodeType.TableKeyString) {
            const k = field.key.name;
            const v = this.formatExpression(field.value, 0);
            fieldStrs.push(`${k}=${v}`);
          } else if (field.type === NodeType.TableValue) {
            fieldStrs.push(this.formatExpression(field.value, 0));
          }
        }
        const sep = this.options.minify ? ',' : ', ';
        code = `{${fieldStrs.join(sep)}}`;
        break;
      }

      default:
        throw new Error(`Unknown expression type: ${node.type}`);
    }

    if (myPrec < parentPrec) {
      return `(${code})`;
    }
    return code;
  }

  needsSpaceAroundOp(op) {
    return op === 'and' || op === 'or' || op === '//' || op === '..';
  }

  escapeString(str) {
    if (typeof str !== 'string') return String(str);
    let res = '';
    for (let i = 0; i < str.length; i++) {
      const code = str.charCodeAt(i);
      if (str[i] === '\\') res += '\\\\';
      else if (str[i] === '"') res += '\\"';
      else if (str[i] === '\n') res += '\\n';
      else if (str[i] === '\r') res += '\\r';
      else if (str[i] === '\t') res += '\\t';
      else if (code < 32 || code > 126) {
        res += `\\${code}`;
      } else {
        res += str[i];
      }
    }
    return res;
  }
}

module.exports = {
  Generator
};
