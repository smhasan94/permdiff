// Upsert one PR comment marked <!-- permdiff -->. Used by actions/github-script.
// module.exports = async ({ github, context, core }, { body, marker }) => ...
const DEFAULT_MARKER = "<!-- permdiff -->";

async function findExisting(github, params, marker) {
  const comments = await github.paginate(github.rest.issues.listComments, {
    ...params,
    per_page: 100,
  });
  return comments.find((c) => typeof c.body === "string" && c.body.startsWith(marker));
}

async function upsertComment({ github, context, core }, { body, marker = DEFAULT_MARKER }) {
  const issue_number = context.issue && context.issue.number;
  if (!issue_number) {
    core.info("no pull request in context; skipping comment");
    return { action: "skipped" };
  }
  const params = { owner: context.repo.owner, repo: context.repo.repo, issue_number };
  const text = body.startsWith(marker) ? body : `${marker}\n${body}`;
  try {
    const existing = await findExisting(github, params, marker);
    if (existing) {
      if (existing.body === text) {
        core.info(`comment ${existing.id} unchanged`);
        return { action: "unchanged", id: existing.id };
      }
      await github.rest.issues.updateComment({ ...params, comment_id: existing.id, body: text });
      core.info(`updated comment ${existing.id}`);
      return { action: "updated", id: existing.id };
    }
    const created = await github.rest.issues.createComment({ ...params, body: text });
    core.info(`created comment ${created.data.id}`);
    return { action: "created", id: created.data.id };
  } catch (err) {
    if (err && (err.status === 403 || err.status === 404)) {
      core.warning(`cannot write PR comments (${err.status}); falling back to the job summary`);
      return { action: "forbidden" };
    }
    throw err;
  }
}

module.exports = upsertComment;
module.exports.DEFAULT_MARKER = DEFAULT_MARKER;
