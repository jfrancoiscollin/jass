#!/usr/bin/env bash
# Technical-only wrapper: run the existing preregistered labels template with
# a JassEngine adapter that enforces --no-book for every fixed-depth search.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"
cd "$JASS_CODE_DIR"
python3 -m py_compile jobs/tools/l3_curriculum_error_loss_first_sibling_labels_nobook.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_loss_first_sibling_labels_nobook
TMP="$JASS_RESULT_DIR/loss-first-labels-nobook-template.sh"
sed 's#jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py#jobs/tools/l3_curriculum_error_loss_first_sibling_labels_nobook.py#g' \
  jobs/templates/l3-curriculum-error-loss-first-sibling-labels-v1.sh > "$TMP"
chmod +x "$TMP"
exec bash "$TMP"
