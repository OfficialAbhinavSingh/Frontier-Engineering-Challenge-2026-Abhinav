| Variant | Cases reproduced byte-identically | Fail-to-Pass recorded | replayed |
| --- | ---: | ---: | ---: |
| `b0` | 27/27 | 5 | 5 |
| `b1` | 8/27 | 6 | 0 |
| `s5` | 15/27 | 9 | 4 |
| `s6` | 17/27 | 8 | 4 |
| `x1` | 9/27 | 10 | 4 |

- `b1` cache miss: click__2817, click__3043, click__3105, jinja__1510, jinja__1521, jinja__1573, jinja__1612, jinja__1701, rich__3796, rich__3881, rich__3943, rich__4041, sqlglot__7949, sqlglot__8225, sqlglot__8244, tomlkit__440, tomlkit__531, tomlkit__542, tomlkit__543
- `s5` cache miss: jinja__1573, jinja__1612, jinja__1701, jinja__2027, rich__3838, rich__3881, rich__3943, rich__4041, rich__5090
- `s5` diverged: tomlkit__542, tomlkit__543, tomlkit__562
- `s6` cache miss: jinja__1573, jinja__1612, jinja__1701, jinja__2027, rich__3838, rich__3881, rich__3943, rich__4041, rich__5090
- `s6` diverged: tomlkit__562
- `x1` cache miss: click__3105, jinja__1573, jinja__1612, jinja__1701, jinja__2027, rich__3838, rich__3881, rich__3943, rich__4041, rich__5090, sqlglot__7949, sqlglot__8225, sqlglot__8244, tomlkit__562
- `x1` diverged: click__2703, click__2817, click__2968, click__3043
