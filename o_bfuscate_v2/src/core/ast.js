// src/core/ast.js
// Luau / Lua Abstract Syntax Tree (AST) Node definitions and traversal utilities

const NodeType = {
  Chunk: 'Chunk',
  
  // Statements
  AssignmentStatement: 'AssignmentStatement',
  CompoundAssignmentStatement: 'CompoundAssignmentStatement',
  LocalStatement: 'LocalStatement',
  FunctionDeclaration: 'FunctionDeclaration',
  LocalFunctionDeclaration: 'LocalFunctionDeclaration',
  ReturnStatement: 'ReturnStatement',
  BreakStatement: 'BreakStatement',
  ContinueStatement: 'ContinueStatement', // Luau
  IfStatement: 'IfStatement',
  WhileStatement: 'WhileStatement',
  DoStatement: 'DoStatement',
  RepeatStatement: 'RepeatStatement',
  ForNumericStatement: 'ForNumericStatement',
  ForGenericStatement: 'ForGenericStatement',
  CallStatement: 'CallStatement',
  TypeAliasStatement: 'TypeAliasStatement', // Luau type annotations
  
  // Expressions
  Identifier: 'Identifier',
  NumericLiteral: 'NumericLiteral',
  StringLiteral: 'StringLiteral',
  BooleanLiteral: 'BooleanLiteral',
  NilLiteral: 'NilLiteral',
  VarargLiteral: 'VarargLiteral',
  InterpolatedStringExpression: 'InterpolatedStringExpression', // Luau `...`
  IfExpression: 'IfExpression', // Luau if cond then val1 else val2
  BinaryExpression: 'BinaryExpression',
  UnaryExpression: 'UnaryExpression',
  LogicalExpression: 'LogicalExpression',
  MemberExpression: 'MemberExpression',
  IndexExpression: 'IndexExpression',
  CallExpression: 'CallExpression',
  TableCallExpression: 'TableCallExpression',
  StringCallExpression: 'StringCallExpression',
  TableConstructorExpression: 'TableConstructorExpression',
  TableKey: 'TableKey',
  TableKeyString: 'TableKeyString',
  TableValue: 'TableValue',
  FunctionExpression: 'FunctionExpression',
  TypeAnnotation: 'TypeAnnotation'
};

class ASTNode {
  constructor(type, props = {}) {
    this.type = type;
    Object.assign(this, props);
  }
}

// AST Walker / Visitor helper
function walk(node, visitor, parent = null, key = null) {
  if (!node || typeof node !== 'object') return;

  if (Array.isArray(node)) {
    for (let i = 0; i < node.length; i++) {
      walk(node[i], visitor, parent, i);
    }
    return;
  }

  // Handle plain clause containers (like IfStatement clauses or IfExpression elseifs)
  if (!node.type) {
    for (const childKey of Object.keys(node)) {
      if (childKey === 'parent' || childKey === 'scope' || childKey === 'symbol' || childKey === 'bodyScope' || childKey === 'type') continue;
      const child = node[childKey];
      if (child && typeof child === 'object') {
        walk(child, visitor, parent, childKey);
      }
    }
    return;
  }

  if (visitor.enter) {
    visitor.enter(node, parent, key);
  }
  if (visitor[node.type]) {
    visitor[node.type](node, parent, key);
  }

  // Explicit structured traversals for complex nodes
  if (node.type === NodeType.IfStatement) {
    if (node.clauses) {
      for (let i = 0; i < node.clauses.length; i++) {
        const clause = node.clauses[i];
        if (clause.condition) walk(clause.condition, visitor, node, 'condition');
        if (clause.body) walk(clause.body, visitor, node, 'body');
      }
    }
    if (node.elseBody) {
      walk(node.elseBody, visitor, node, 'elseBody');
    }
  } else if (node.type === NodeType.IfExpression) {
    if (node.condition) walk(node.condition, visitor, node, 'condition');
    if (node.trueExpression) walk(node.trueExpression, visitor, node, 'trueExpression');
    if (node.elseifs) {
      for (let i = 0; i < node.elseifs.length; i++) {
        const elif = node.elseifs[i];
        if (elif.condition) walk(elif.condition, visitor, node, 'condition');
        if (elif.expression) walk(elif.expression, visitor, node, 'expression');
      }
    }
    if (node.falseExpression) walk(node.falseExpression, visitor, node, 'falseExpression');
  } else {
    // Traverse all child properties
    for (const childKey of Object.keys(node)) {
      if (childKey === 'parent' || childKey === 'scope' || childKey === 'symbol' || childKey === 'bodyScope' || childKey === 'type') continue;
      const child = node[childKey];
      if (child && typeof child === 'object') {
        walk(child, visitor, node, childKey);
      }
    }
  }

  if (visitor.leave) {
    visitor.leave(node, parent, key);
  }
}

// Clone AST node deeply
function cloneNode(node) {
  if (!node || typeof node !== 'object') return node;
  if (Array.isArray(node)) return node.map(cloneNode);

  const copy = new ASTNode(node.type);
  for (const key of Object.keys(node)) {
    if (key === 'scope' || key === 'parent') continue;
    copy[key] = cloneNode(node[key]);
  }
  return copy;
}

module.exports = {
  NodeType,
  ASTNode,
  walk,
  cloneNode
};
