- `xippios-mcp[faostat]`, `[cashctrl]` and `[usda-esr]` install the three sources that proved
  xippios-core 0.5.0 with the host, each from its first release on core 0.5 (`>=0.3.0`,
  `>=0.6.0` and `>=0.4.0`), and `all` installs the three, where 0.1.0 named nine extras on
  core 0.3: `comtrade`, `eurostat`, `usda-esmis`, `usda-gats`, `usda-nass` and `usda-psd`
  have no extra until the next release lists all twelve sources. The image installs `all`
  from `uv.lock` and serves the three. sdk-usda-esr brings `xippios-usda-fas` as its
  dependency, of which the host serves nothing.
  (https://github.com/xippios/xippios-mcp/issues/32)
