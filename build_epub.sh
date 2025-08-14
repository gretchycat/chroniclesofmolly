#!/bin/bash

# --- Check for yq binary ---
if ! command -v yq &>/dev/null; then
  echo "❌ 'yq' is not installed. Please install the Go-based version:"
  echo "   https://github.com/mikefarah/yq"
  exit 1
fi

# --- Confirm Go-based yq ---
if ! yq --version | grep -qi 'mikefarah'; then
  echo "❌ Detected yq is not the Go-based version (required)."
  echo "   You may have the Python wrapper installed instead."
  echo "   See: https://github.com/mikefarah/yq"
  exit 1
fi

# --- Load metadata from YAML ---
METADATA_FILE="metadata.yaml"
if [ ! -f "$METADATA_FILE" ]; then
  echo "❌ Metadata file '$METADATA_FILE' not found."
  exit 1
fi

TITLE=$(yq '.title' "$METADATA_FILE")
AUTHOR=$(yq '.author' "$METADATA_FILE")
OUTPUT=$(yq ".output // \"$TITLE.epub\"" "$METADATA_FILE")
PDFOUTPUT=$(yq ".output // \"$TITLE.pdf\"" "$METADATA_FILE")
COVER=$(yq '.cover // "cover.png"' "$METADATA_FILE")
CSS=$(yq '.css // "style.css' "$METADATA_FILE")

rm -f "$OUTPUT"

# --- Gather Markdown files ---
CHAPTERS=$(ls [0-9][0-9][0-9]*.md 2>/dev/null | sort)
PRE=$(ls pre-[0-9][0-9][0-9]*.md 2>/dev/null | sort)
POST=$(ls post-[0-9][0-9][0-9]*.md 2>/dev/null | sort)

echo "📚 Detected pre-chapters:"
for file in $PRE; do
  title=$(grep -m 1 '^# ' "$file" | sed 's/^# //')
  printf " - %s → %s\n" "$file" "$title"
done

echo "📚 Detected chapters:"
for file in $CHAPTERS; do
  title=$(grep -m 1 '^# ' "$file" | sed 's/^# //')
  printf " - %s → %s\n" "$file" "$title"
done

echo "📚 Detected post-chapters:"
for file in $POST; do
  title=$(grep -m 1 '^# ' "$file" | sed 's/^# //')
  printf " - %s → %s\n" "$file" "$title"
done


# --- Construct Pandoc command ---
CMD="pandoc"

[ -n "$PRE" ] && CMD+=" $PRE"
CMD+=" $CHAPTERS $APPENDICES"
[ -n "$POST" ] && CMD+=" $POST"

CMD+=" -o \"$OUTPUT\" --toc"
#CMD+=" --metadata title=\"$TITLE\""
#CMD+=" --metadata author=\"$AUTHOR\""

if [ -f "$COVER" ]; then
  CMD+=" --epub-cover-image=\"$COVER\""
  echo "✅ Using cover image: $COVER"
fi

if [ -f "$METADATA_FILE" ]; then
    CMD+=" --metadata-file=metadata.yaml"
fi

if [ -f "$CSS" ]; then
  CMD+=" --css=\"$CSS\""
  echo "✅ Using stylesheet: $CSS"
fi

# --- Run the command ---
echo "📘 Generating EPUB: $OUTPUT"
eval $CMD

if [ -f "$OUTPUT" ]; then
  echo "🎉 EPUB created successfully: $OUTPUT"
else
  echo "❌ Something went wrong."
fi
