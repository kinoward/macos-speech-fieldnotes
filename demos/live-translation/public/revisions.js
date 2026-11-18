export function applyRevision(segment, message) {
  const { type, revision } = message;
  const final = message.final === true;
  const text = message.text.trim();

  if (type === "source") {
    if (revision < segment.sourceRevision) return false;
    if (revision === segment.sourceRevision && segment.sourceFinal && !final) return false;

    if (revision > segment.sourceRevision && segment.translationRevision < revision) {
      const previousSource = segment.source.textContent;
      if (previousSource && !text.startsWith(previousSource)) {
        segment.translation.textContent = "";
        segment.translationRevision = -1;
      }
      // Keep a translation only while the source grows by appending, including an unchanged final update.
      segment.translationFinal = false;
      segment.translation.dataset.final = "false";
    }
    segment.sourceRevision = revision;
    segment.sourceFinal = final;
    segment.source.textContent = text;
    segment.source.dataset.final = String(final);
  } else {
    // A late translation cannot replace the preview retained for a newer source revision.
    if (revision !== segment.sourceRevision) return false;
    if (revision < segment.translationRevision) return false;
    if (revision === segment.translationRevision && segment.translationFinal && !final) return false;
    if (final && !segment.sourceFinal) return false;

    segment.translationRevision = revision;
    segment.translationFinal = final;
    segment.translation.textContent = text;
    segment.translation.dataset.final = String(final);
  }
  return true;
}
