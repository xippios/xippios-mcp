- Each release publishes the host's image to the GitHub Container Registry, tagged with its
  version alone and no `latest`, so an operator pulls `ghcr.io/xippios/xippios-mcp:0.2.0`
  where 0.1.0 had the image built from a checkout. The image carries the labels
  `org.opencontainers.image.source`, `.version` and `.revision`, which name the repository,
  the version and the commit that the release tagged.
  (https://github.com/xippios/xippios-mcp/issues/38)
