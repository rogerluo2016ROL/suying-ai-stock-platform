;; Python tree-sitter query（声明式参考，04 §3.1 / §4.1）
;; 注：python_adapter.py 当前用 AST 遍历实现（避 tree-sitter 0.26 Query API 版本差异）；
;;     本文件是 query 的声明式 SSOT，未来切 Query 实现时直接 load。

;; 符号提取
(function_definition name: (identifier) @fn.name) @fn.def
(class_definition    name: (identifier) @cls.name) @cls.def
(decorated_definition definition: (function_definition name: (identifier) @fn.name)) @fn.def

;; import 提取
(import_statement)      @import.std      ; import a.b.c
(import_from_statement) @import.from     ; from a.b import c, from . import x
