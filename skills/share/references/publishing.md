# Optional GitHub Pages publication

Create the card locally by default. Publish only when the user explicitly requests a public link. Public HTML includes all embedded asset bytes; Pages does not provide automatic expiration.

If `quick-share` is installed, it manages the user's dedicated [share repository](https://github.com/pkronstrom/share):

```sh
quick-share publish /absolute/path/card.html --name foxyasset --preview /absolute/path/preview.png
quick-share list
quick-share unshare foxyasset
```

Use a clear screenshot preview for chat link unfurls. The CLI adds Open Graph metadata, preserves the card's embedded originals, pushes only its own changes, and waits for the matching Pages build. Give the direct card URL from its JSON output. Chat services decide whether to display a preview.

The same publication is a safe retry. Different content under the same name needs `--replace`. `--dry-run` previews without writes or network publication. A dirty sharing checkout stops mutations; preserve the edits rather than resetting it. If a Git push fails, fix the cause and retry the same command.

Unsharing removes the live file through a new Pages deployment; Git history, forks, caches and downloaded copies can remain. Do not describe it as revocation or timed access. For other users or hosts, follow their configured static publishing workflow; don't assume this personal repository is their destination.
