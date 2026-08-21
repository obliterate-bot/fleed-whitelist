// src/core/scope.js
// Scope Analyzer and Symbol Tracker for Luau / Lua AST

const { NodeType, walk } = require('./ast');

class Scope {
  constructor(parent = null, isFunction = false) {
    this.parent = parent;
    this.isFunction = isFunction;
    this.children = [];
    this.declarations = new Map(); // name -> { node, references: [] }
    this.references = []; // [{ name, node }]
    this.upvalues = new Set(); // names captured from outer function
    this.globals = new Set(); // referenced globals

    if (parent) {
      parent.children.push(this);
    }
  }

  declare(name, node) {
    const symbol = {
      name,
      node,
      references: [],
      mangledName: null
    };
    this.declarations.set(name, symbol);
    return symbol;
  }

  lookup(name) {
    if (this.declarations.has(name)) {
      return { scope: this, symbol: this.declarations.get(name), isUpvalue: false };
    }
    if (this.parent) {
      const res = this.parent.lookup(name);
      if (res) {
        // If crossing a function boundary, mark as upvalue
        if (this.isFunction) {
          this.upvalues.add(name);
        }
        return {
          scope: res.scope,
          symbol: res.symbol,
          isUpvalue: this.isFunction || res.isUpvalue
        };
      }
    }
    return null;
  }

  isDeclared(name) {
    return this.declarations.has(name) || (this.parent && this.parent.isDeclared(name));
  }
}

class ScopeAnalyzer {
  constructor(ast) {
    this.ast = ast;
    this.rootScope = new Scope(null, true);
    this.allScopes = [this.rootScope];
    this.currentScope = this.rootScope;
  }

  analyze() {
    this.walkNode(this.ast, this.rootScope);
    return {
      rootScope: this.rootScope,
      allScopes: this.allScopes
    };
  }

  enterScope(isFunction = false) {
    const newScope = new Scope(this.currentScope, isFunction);
    this.allScopes.push(newScope);
    this.currentScope = newScope;
    return newScope;
  }

  exitScope() {
    if (this.currentScope.parent) {
      this.currentScope = this.currentScope.parent;
    }
  }

  walkNode(node, scope) {
    if (!node || typeof node !== 'object') return;

    node.scope = this.currentScope;

    switch (node.type) {
      case NodeType.LocalStatement: {
        // First evaluate init expressions in current scope
        for (const initExpr of node.init) {
          this.walkNode(initExpr, this.currentScope);
        }
        // Then declare the variables
        for (const v of node.variables) {
          this.currentScope.declare(v.name, v);
        }
        break;
      }

      case NodeType.LocalFunctionDeclaration: {
        // Declare the function in the current scope
        this.currentScope.declare(node.identifier.name, node.identifier);
        
        // Enter function body scope
        this.enterScope(true);
        node.bodyScope = this.currentScope;
        for (const p of node.parameters) {
          this.currentScope.declare(p.name, p);
        }
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.FunctionDeclaration: {
        // Identifier can be a member expression or global
        this.walkNode(node.identifier, this.currentScope);

        // Enter function body scope
        this.enterScope(true);
        node.bodyScope = this.currentScope;
        if (node.isMethod) {
          this.currentScope.declare('self', null);
        }
        for (const p of node.parameters) {
          this.currentScope.declare(p.name, p);
        }
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.FunctionExpression: {
        this.enterScope(true);
        node.bodyScope = this.currentScope;
        for (const p of node.parameters) {
          this.currentScope.declare(p.name, p);
        }
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.DoStatement: {
        this.enterScope(false);
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.IfStatement: {
        for (const clause of node.clauses) {
          this.walkNode(clause.condition, this.currentScope);
          this.enterScope(false);
          for (const stmt of clause.body) {
            this.walkNode(stmt, this.currentScope);
          }
          this.exitScope();
        }
        if (node.elseBody) {
          this.enterScope(false);
          for (const stmt of node.elseBody) {
            this.walkNode(stmt, this.currentScope);
          }
          this.exitScope();
        }
        break;
      }

      case NodeType.DoStatement: {
        this.enterScope(false);
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.WhileStatement: {
        this.walkNode(node.condition, this.currentScope);
        this.enterScope(false);
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.RepeatStatement: {
        this.enterScope(false);
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.walkNode(node.condition, this.currentScope);
        this.exitScope();
        break;
      }

      case NodeType.ForNumericStatement: {
        this.walkNode(node.start, this.currentScope);
        this.walkNode(node.end, this.currentScope);
        if (node.step) this.walkNode(node.step, this.currentScope);

        this.enterScope(false);
        this.currentScope.declare(node.variable.name, node.variable);
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.ForGenericStatement: {
        for (const it of node.iterators) {
          this.walkNode(it, this.currentScope);
        }
        this.enterScope(false);
        for (const v of node.variables) {
          this.currentScope.declare(v.name, v);
        }
        for (const stmt of node.body) {
          this.walkNode(stmt, this.currentScope);
        }
        this.exitScope();
        break;
      }

      case NodeType.Identifier: {
        const name = node.name;
        const res = this.currentScope.lookup(name);
        if (res) {
          res.symbol.references.push(node);
          node.symbol = res.symbol;
        } else {
          this.currentScope.globals.add(name);
          this.rootScope.globals.add(name);
          node.isGlobal = true;
        }
        break;
      }

      case NodeType.MemberExpression: {
        this.walkNode(node.base, this.currentScope);
        // Do not lookup node.identifier as a variable (it is a property name)
        break;
      }

      case NodeType.TableKeyString: {
        // Key is string identifier, value is expression
        this.walkNode(node.value, this.currentScope);
        break;
      }

      default: {
        for (const key of Object.keys(node)) {
          if (key === 'scope' || key === 'parent' || key === 'symbol' || key === 'type') continue;
          const child = node[key];
          if (Array.isArray(child)) {
            for (const item of child) {
              this.walkNode(item, this.currentScope);
            }
          } else if (child && typeof child === 'object') {
            this.walkNode(child, this.currentScope);
          }
        }
      }
    }
  }
}

module.exports = {
  Scope,
  ScopeAnalyzer
};
