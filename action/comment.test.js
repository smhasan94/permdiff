const test = require("node:test");
const assert = require("node:assert/strict");
const upsert = require("./comment.js");

function harness({ comments = [], failWith = null } = {}) {
  const calls = [];
  const github = {
    paginate: async (fn, params) => fn(params),
    rest: {
      issues: {
        listComments: async () => comments,
        updateComment: async (p) => {
          calls.push(["update", p]);
          if (failWith) throw failWith;
          return { data: { id: p.comment_id } };
        },
        createComment: async (p) => {
          calls.push(["create", p]);
          if (failWith) throw failWith;
          return { data: { id: 42 } };
        },
      },
    },
  };
  const context = { issue: { number: 7 }, repo: { owner: "o", repo: "r" } };
  const logs = [];
  const core = { info: (m) => logs.push(m), warning: (m) => logs.push("warn:" + m) };
  return { github, context, core, calls, logs };
}

test("creates a marked comment when none exists", async () => {
  const h = harness();
  const result = await upsert(h, { body: "hello" });
  assert.deepEqual(result, { action: "created", id: 42 });
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0][1].body, "<!-- permdiff -->\nhello");
  assert.equal(h.calls[0][1].issue_number, 7);
});

test("updates the existing marked comment in place, ignoring other comments", async () => {
  const h = harness({
    comments: [
      { id: 1, body: "unrelated" },
      { id: 2, body: "<!-- permdiff -->\nold" },
    ],
  });
  const result = await upsert(h, { body: "<!-- permdiff -->\nnew" });
  assert.deepEqual(result, { action: "updated", id: 2 });
  assert.equal(h.calls[0][0], "update");
  assert.equal(h.calls[0][1].comment_id, 2);
});

test("is a no-op when the body is unchanged", async () => {
  const h = harness({ comments: [{ id: 2, body: "<!-- permdiff -->\nsame" }] });
  const result = await upsert(h, { body: "<!-- permdiff -->\nsame" });
  assert.deepEqual(result, { action: "unchanged", id: 2 });
  assert.equal(h.calls.length, 0);
});

test("falls back on 403 instead of failing", async () => {
  const h = harness({ failWith: Object.assign(new Error("Resource not accessible"), { status: 403 }) });
  const result = await upsert(h, { body: "x" });
  assert.deepEqual(result, { action: "forbidden" });
  assert.ok(h.logs.some((l) => l.startsWith("warn:")));
});

test("rethrows other errors", async () => {
  const h = harness({ failWith: Object.assign(new Error("boom"), { status: 500 }) });
  await assert.rejects(() => upsert(h, { body: "x" }), /boom/);
});

test("skips when there is no pull request", async () => {
  const h = harness();
  h.context.issue = undefined;
  assert.deepEqual(await upsert(h, { body: "x" }), { action: "skipped" });
});
