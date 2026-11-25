- The host serves sdk-faostat, sdk-cashctrl and sdk-usda-esr as their own servers serve them,
  which a test proves wherever they are installed beside it: each loads by its `build()`, and
  every endpoint of them lists the tools under the names and with the input schemas of the
  source's own server. A dated report under `docs/reports/` records a run of it on
  xippios-core 0.5.0 before its release, with one call of each source during which the run
  counted no request.
  (https://github.com/xippios/xippios-mcp/issues/28)
