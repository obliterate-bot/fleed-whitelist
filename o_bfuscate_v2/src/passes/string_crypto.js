// src/passes/string_crypto.js
// High-Performance / Zero-Overhead Luau Buffer String Encryption Engine

const { NodeType, ASTNode, walk } = require('../core/ast');

class StringCryptoPass {
  constructor(options = {}) {
    this.options = {
      mode: options.stringMode || 'buffer_memoized', // 'buffer_memoized' | 'inlined_buffer' | 'table_xor'
      key1: options.key1 || (Math.floor(Math.random() * 200) + 25),
      key2: options.key2 || (Math.floor(Math.random() * 15) + 3),
      ...options
    };
    this.strings = [];
    this.stringIndexMap = new Map();
  }

  encryptString(str, key1, key2, offset) {
    const bytes = [];
    for (let i = 0; i < str.length; i++) {
      const b = str.charCodeAt(i);
      const mask = (key1 + ((offset + i) * key2)) & 0xFF;
      bytes.push(b ^ mask);
    }
    return bytes;
  }

  apply(ast) {
    const stringLiterals = [];

    // Collect all string literals
    walk(ast, {
      enter: (node, parent) => {
        if (node.type === NodeType.StringLiteral) {
          // Don't encrypt empty strings or directive strings
          if (node.value.length === 0) return;
          stringLiterals.push({ node, parent });
        }
      }
    });

    if (stringLiterals.length === 0) return ast;

    // Deduplicate strings
    const uniqueStrings = [];
    for (const { node } of stringLiterals) {
      if (!this.stringIndexMap.has(node.value)) {
        const idx = uniqueStrings.length + 1; // 1-indexed for Lua
        uniqueStrings.push(node.value);
        this.stringIndexMap.set(node.value, idx);
      }
    }

    // Build packed byte blob and offset table
    const allBytes = [];
    const stringMeta = []; // { offset, length }

    const key1 = this.options.key1;
    const key2 = this.options.key2;

    for (const str of uniqueStrings) {
      const offset = allBytes.length;
      const encBytes = this.encryptString(str, key1, key2, offset);
      allBytes.push(...encBytes);
      stringMeta.push({ offset, length: str.length });
    }

    // Replace StringLiteral nodes with table lookups `_S[idx]`
    const stringTableName = '_S';

    for (const { node } of stringLiterals) {
      const idx = this.stringIndexMap.get(node.value);
      if (idx !== undefined) {
        node.type = NodeType.IndexExpression;
        node.base = new ASTNode(NodeType.Identifier, { name: stringTableName });
        node.index = new ASTNode(NodeType.NumericLiteral, { value: idx, raw: String(idx) });
        delete node.value;
      }
    }

    // Generate the one-shot buffer decryptor statement
    const decryptorStatement = this.generateDecryptorAST(
      stringTableName,
      allBytes,
      stringMeta,
      key1,
      key2
    );

    // Prepend to AST body
    ast.body.unshift(decryptorStatement);

    return ast;
  }

  generateDecryptorAST(tableName, allBytes, stringMeta, key1, key2) {
    // Luau Buffer Decryption preamble:
    // local _S = (function(bytes, meta, k1, k2)
    //   local b = buffer.create(#bytes)
    //   for i = 1, #bytes do
    //     local mask = (k1 + (i - 1) * k2) % 256
    //     local raw = bit32.bxor(bytes[i], mask)
    //     buffer.writeu8(b, i - 1, raw)
    //   end
    //   local tbl = {}
    //   for idx = 1, #meta, 2 do
    //     tbl[(idx + 1) // 2] = buffer.readstring(b, meta[idx], meta[idx + 1])
    //   end
    //   return tbl
    // end)({ ...bytes }, { ...meta }, k1, k2)

    const metaArray = [];
    for (const m of stringMeta) {
      metaArray.push(m.offset);
      metaArray.push(m.length);
    }

    // Create AST nodes for the packed data
    const bytesFields = allBytes.map(b => new ASTNode(NodeType.TableValue, {
      value: new ASTNode(NodeType.NumericLiteral, { value: b, raw: String(b) })
    }));

    const metaFields = metaArray.map(n => new ASTNode(NodeType.TableValue, {
      value: new ASTNode(NodeType.NumericLiteral, { value: n, raw: String(n) })
    }));

    // Universal high-performance decoder function that works with Luau buffer or Lua 5.1 string.char
    const decoderFunc = new ASTNode(NodeType.FunctionExpression, {
      parameters: [
        new ASTNode(NodeType.Identifier, { name: 'B' }),
        new ASTNode(NodeType.Identifier, { name: 'M' }),
        new ASTNode(NodeType.Identifier, { name: 'k1' }),
        new ASTNode(NodeType.Identifier, { name: 'k2' })
      ],
      isVararg: false,
      body: [
        // local res = {}
        new ASTNode(NodeType.LocalStatement, {
          variables: [new ASTNode(NodeType.Identifier, { name: 'res' })],
          init: [new ASTNode(NodeType.TableConstructorExpression, { fields: [] })]
        }),
        // if typeof(buffer) == "table" or typeof(buffer) == "userdata" or buffer ~= nil then
        // Luau fast-path buffer decoding:
        new ASTNode(NodeType.IfStatement, {
          clauses: [{
            condition: new ASTNode(NodeType.BinaryExpression, {
              operator: '~=',
              left: new ASTNode(NodeType.Identifier, { name: 'buffer' }),
              right: new ASTNode(NodeType.NilLiteral, { value: null, raw: 'nil' })
            }),
            body: [
              // local buf = buffer.create(#B)
              new ASTNode(NodeType.LocalStatement, {
                variables: [new ASTNode(NodeType.Identifier, { name: 'buf' })],
                init: [new ASTNode(NodeType.CallExpression, {
                  base: new ASTNode(NodeType.MemberExpression, {
                    base: new ASTNode(NodeType.Identifier, { name: 'buffer' }),
                    identifier: new ASTNode(NodeType.Identifier, { name: 'create' }),
                    indexer: '.'
                  }),
                  arguments: [new ASTNode(NodeType.UnaryExpression, {
                    operator: '#',
                    argument: new ASTNode(NodeType.Identifier, { name: 'B' })
                  })]
                })]
              }),
              // for i = 1, #B do buffer.writeu8(buf, i - 1, (B[i] - (k1 + (i - 1) * k2)) % 256) end
              // using bit32.bxor
              new ASTNode(NodeType.ForNumericStatement, {
                variable: new ASTNode(NodeType.Identifier, { name: 'i' }),
                start: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' }),
                end: new ASTNode(NodeType.UnaryExpression, {
                  operator: '#',
                  argument: new ASTNode(NodeType.Identifier, { name: 'B' })
                }),
                step: null,
                body: [
                  new ASTNode(NodeType.CallStatement, {
                    expression: new ASTNode(NodeType.CallExpression, {
                      base: new ASTNode(NodeType.MemberExpression, {
                        base: new ASTNode(NodeType.Identifier, { name: 'buffer' }),
                        identifier: new ASTNode(NodeType.Identifier, { name: 'writeu8' }),
                        indexer: '.'
                      }),
                      arguments: [
                        new ASTNode(NodeType.Identifier, { name: 'buf' }),
                        new ASTNode(NodeType.BinaryExpression, {
                          operator: '-',
                          left: new ASTNode(NodeType.Identifier, { name: 'i' }),
                          right: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' })
                        }),
                        new ASTNode(NodeType.CallExpression, {
                          base: new ASTNode(NodeType.MemberExpression, {
                            base: new ASTNode(NodeType.Identifier, { name: 'bit32' }),
                            identifier: new ASTNode(NodeType.Identifier, { name: 'bxor' }),
                            indexer: '.'
                          }),
                          arguments: [
                            new ASTNode(NodeType.IndexExpression, {
                              base: new ASTNode(NodeType.Identifier, { name: 'B' }),
                              index: new ASTNode(NodeType.Identifier, { name: 'i' })
                            }),
                            new ASTNode(NodeType.BinaryExpression, {
                              operator: '%',
                              left: new ASTNode(NodeType.BinaryExpression, {
                                operator: '+',
                                left: new ASTNode(NodeType.Identifier, { name: 'k1' }),
                                right: new ASTNode(NodeType.BinaryExpression, {
                                  operator: '*',
                                  left: new ASTNode(NodeType.BinaryExpression, {
                                    operator: '-',
                                    left: new ASTNode(NodeType.Identifier, { name: 'i' }),
                                    right: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' })
                                  }),
                                  right: new ASTNode(NodeType.Identifier, { name: 'k2' })
                                })
                              }),
                              right: new ASTNode(NodeType.NumericLiteral, { value: 256, raw: '256' })
                            })
                          ]
                        })
                      ]
                    })
                  })
                ]
              }),
              // for idx = 1, #M, 2 do res[(idx + 1) // 2] = buffer.readstring(buf, M[idx], M[idx+1]) end
              new ASTNode(NodeType.ForNumericStatement, {
                variable: new ASTNode(NodeType.Identifier, { name: 'idx' }),
                start: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' }),
                end: new ASTNode(NodeType.UnaryExpression, {
                  operator: '#',
                  argument: new ASTNode(NodeType.Identifier, { name: 'M' })
                }),
                step: new ASTNode(NodeType.NumericLiteral, { value: 2, raw: '2' }),
                body: [
                  new ASTNode(NodeType.AssignmentStatement, {
                    variables: [
                      new ASTNode(NodeType.IndexExpression, {
                        base: new ASTNode(NodeType.Identifier, { name: 'res' }),
                        index: new ASTNode(NodeType.BinaryExpression, {
                          operator: '//',
                          left: new ASTNode(NodeType.BinaryExpression, {
                            operator: '+',
                            left: new ASTNode(NodeType.Identifier, { name: 'idx' }),
                            right: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' })
                          }),
                          right: new ASTNode(NodeType.NumericLiteral, { value: 2, raw: '2' })
                        })
                      })
                    ],
                    init: [
                      new ASTNode(NodeType.CallExpression, {
                        base: new ASTNode(NodeType.MemberExpression, {
                          base: new ASTNode(NodeType.Identifier, { name: 'buffer' }),
                          identifier: new ASTNode(NodeType.Identifier, { name: 'readstring' }),
                          indexer: '.'
                        }),
                        arguments: [
                          new ASTNode(NodeType.Identifier, { name: 'buf' }),
                          new ASTNode(NodeType.IndexExpression, {
                            base: new ASTNode(NodeType.Identifier, { name: 'M' }),
                            index: new ASTNode(NodeType.Identifier, { name: 'idx' })
                          }),
                          new ASTNode(NodeType.IndexExpression, {
                            base: new ASTNode(NodeType.Identifier, { name: 'M' }),
                            index: new ASTNode(NodeType.BinaryExpression, {
                              operator: '+',
                              left: new ASTNode(NodeType.Identifier, { name: 'idx' }),
                              right: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' })
                            })
                          })
                        ]
                      })
                    ]
                  })
                ]
              })
            ]
          }],
          // Fallback for environments without buffer library (Lua 5.1/LuaJIT fallback)
          elseBody: [
            new ASTNode(NodeType.ForNumericStatement, {
              variable: new ASTNode(NodeType.Identifier, { name: 'idx' }),
              start: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' }),
              end: new ASTNode(NodeType.UnaryExpression, {
                operator: '#',
                argument: new ASTNode(NodeType.Identifier, { name: 'M' })
              }),
              step: new ASTNode(NodeType.NumericLiteral, { value: 2, raw: '2' }),
              body: [
                new ASTNode(NodeType.LocalStatement, {
                  variables: [
                    new ASTNode(NodeType.Identifier, { name: 'off' }),
                    new ASTNode(NodeType.Identifier, { name: 'len' }),
                    new ASTNode(NodeType.Identifier, { name: 'chars' })
                  ],
                  init: [
                    new ASTNode(NodeType.IndexExpression, {
                      base: new ASTNode(NodeType.Identifier, { name: 'M' }),
                      index: new ASTNode(NodeType.Identifier, { name: 'idx' })
                    }),
                    new ASTNode(NodeType.IndexExpression, {
                      base: new ASTNode(NodeType.Identifier, { name: 'M' }),
                      index: new ASTNode(NodeType.BinaryExpression, {
                        operator: '+',
                        left: new ASTNode(NodeType.Identifier, { name: 'idx' }),
                        right: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' })
                      })
                    }),
                    new ASTNode(NodeType.TableConstructorExpression, { fields: [] })
                  ]
                }),
                new ASTNode(NodeType.ForNumericStatement, {
                  variable: new ASTNode(NodeType.Identifier, { name: 'j' }),
                  start: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' }),
                  end: new ASTNode(NodeType.Identifier, { name: 'len' }),
                  step: null,
                  body: [
                    new ASTNode(NodeType.LocalStatement, {
                      variables: [new ASTNode(NodeType.Identifier, { name: 'pos' })],
                      init: [new ASTNode(NodeType.BinaryExpression, {
                        operator: '+',
                        left: new ASTNode(NodeType.Identifier, { name: 'off' }),
                        right: new ASTNode(NodeType.Identifier, { name: 'j' })
                      })]
                    }),
                    new ASTNode(NodeType.LocalStatement, {
                      variables: [new ASTNode(NodeType.Identifier, { name: 'mask' })],
                      init: [new ASTNode(NodeType.BinaryExpression, {
                        operator: '%',
                        left: new ASTNode(NodeType.BinaryExpression, {
                          operator: '+',
                          left: new ASTNode(NodeType.Identifier, { name: 'k1' }),
                          right: new ASTNode(NodeType.BinaryExpression, {
                            operator: '*',
                            left: new ASTNode(NodeType.BinaryExpression, {
                              operator: '-',
                              left: new ASTNode(NodeType.Identifier, { name: 'pos' }),
                              right: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' })
                            }),
                            right: new ASTNode(NodeType.Identifier, { name: 'k2' })
                          })
                        }),
                        right: new ASTNode(NodeType.NumericLiteral, { value: 256, raw: '256' })
                      })]
                    }),
                    new ASTNode(NodeType.AssignmentStatement, {
                      variables: [new ASTNode(NodeType.IndexExpression, {
                        base: new ASTNode(NodeType.Identifier, { name: 'chars' }),
                        index: new ASTNode(NodeType.Identifier, { name: 'j' })
                      })],
                      init: [new ASTNode(NodeType.CallExpression, {
                        base: new ASTNode(NodeType.MemberExpression, {
                          base: new ASTNode(NodeType.Identifier, { name: 'string' }),
                          identifier: new ASTNode(NodeType.Identifier, { name: 'char' }),
                          indexer: '.'
                        }),
                        arguments: [new ASTNode(NodeType.CallExpression, {
                          base: new ASTNode(NodeType.MemberExpression, {
                            base: new ASTNode(NodeType.Identifier, { name: 'bit32' }),
                            identifier: new ASTNode(NodeType.Identifier, { name: 'bxor' }),
                            indexer: '.'
                          }),
                          arguments: [
                            new ASTNode(NodeType.IndexExpression, {
                              base: new ASTNode(NodeType.Identifier, { name: 'B' }),
                              index: new ASTNode(NodeType.Identifier, { name: 'pos' })
                            }),
                            new ASTNode(NodeType.Identifier, { name: 'mask' })
                          ]
                        })]
                      })]
                    })
                  ]
                }),
                new ASTNode(NodeType.AssignmentStatement, {
                  variables: [new ASTNode(NodeType.IndexExpression, {
                    base: new ASTNode(NodeType.Identifier, { name: 'res' }),
                    index: new ASTNode(NodeType.BinaryExpression, {
                      operator: '//',
                      left: new ASTNode(NodeType.BinaryExpression, {
                        operator: '+',
                        left: new ASTNode(NodeType.Identifier, { name: 'idx' }),
                        right: new ASTNode(NodeType.NumericLiteral, { value: 1, raw: '1' })
                      }),
                      right: new ASTNode(NodeType.NumericLiteral, { value: 2, raw: '2' })
                    })
                  })],
                  init: [new ASTNode(NodeType.CallExpression, {
                    base: new ASTNode(NodeType.MemberExpression, {
                      base: new ASTNode(NodeType.Identifier, { name: 'table' }),
                      identifier: new ASTNode(NodeType.Identifier, { name: 'concat' }),
                      indexer: '.'
                    }),
                    arguments: [new ASTNode(NodeType.Identifier, { name: 'chars' })]
                  })]
                })
              ]
            })
          ]
        }),
        // return res
        new ASTNode(NodeType.ReturnStatement, {
          arguments: [new ASTNode(NodeType.Identifier, { name: 'res' })]
        })
      ]
    });

    return new ASTNode(NodeType.LocalStatement, {
      variables: [new ASTNode(NodeType.Identifier, { name: tableName })],
      init: [
        new ASTNode(NodeType.CallExpression, {
          base: decoderFunc,
          arguments: [
            new ASTNode(NodeType.TableConstructorExpression, { fields: bytesFields }),
            new ASTNode(NodeType.TableConstructorExpression, { fields: metaFields }),
            new ASTNode(NodeType.NumericLiteral, { value: key1, raw: String(key1) }),
            new ASTNode(NodeType.NumericLiteral, { value: key2, raw: String(key2) })
          ]
        })
      ]
    });
  }
}

module.exports = {
  StringCryptoPass
};
