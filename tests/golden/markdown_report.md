<!-- permdiff -->
## permdiff: `origin/main` → `HEAD`

**14 calls** · 2026-09-18 → 2026-09-22 · policy `policy` · engine `opa`  
base `0123456789ab` · head `89abcdef0123` · salt `000102030405060708090a0b0c0d0e0f`

| Transition | Count | Top |
|---|---:|---|
| newly DENIED | 3 | `aws.ec2.terminate_instance` |
| newly ALLOWED ⚠ widening | 2 | `github.delete_branch` |
| now REQUIRE_APPROVAL ⚠ widening | 2 | `stripe.refund` |
| attribution changed | 1 | `github.read` |
| can't evaluate | 2 | `missing context: principal.department` |
| unchanged | 4 |  |

<details>
<summary>⚠ widening · <code>github.delete_branch</code> · 2 calls · deny → allow</summary>

Reasons: branch protection removed

| Call | Principal | Arguments | Reasons |
|---|---|---|---|
| `call-001` | `principal:6d614a89` | `{"branch": "<str:21>"}` | branch protection removed |
| `call-002` | `principal:6d614a89` | `{"branch": "<str:21>"}` | branch protection removed |

</details>

<details>
<summary>⚠ widening · <code>stripe.refund</code> · 1 call · deny → require_approval</summary>

Reasons: amount>500

| Call | Principal | Arguments | Reasons |
|---|---|---|---|
| `call-003` | `principal:6d614a89` | `{"amount": "<int>"}` | amount>500 |

</details>

<details>
<summary>tightening · <code>aws.ec2.terminate_instance</code> · 3 calls · allow → deny</summary>

Reasons: prod instances locked

| Call | Principal | Arguments | Reasons |
|---|---|---|---|
| `call-004` | `principal:6d614a89` | `{"meta": {"n": "<str:24>"}, "target": "<str:21>"}` | prod instances locked |
| `call-005` | `principal:6d614a89` | `{"meta": {"n": "<str:24>"}, "target": "<str:21>"}` | prod instances locked |
| `call-006` | `principal:6d614a89` | `{"meta": {"n": "<str:24>"}, "target": "<str:21>"}` | prod instances locked |

</details>

<details>
<summary>tightening · <code>stripe.refund</code> · 1 call · allow → require_approval</summary>

Reasons: amount>500

| Call | Principal | Arguments | Reasons |
|---|---|---|---|
| `call-007` | `principal:6d614a89` | `{"amount": "<int>"}` | amount>500 |

</details>

<details>
<summary>can't evaluate · <code>salesforce.update</code> · 2 calls · allow → error</summary>

Reasons: principal.department

| Call | Principal | Arguments | Reasons |
|---|---|---|---|
| `call-008` | `principal:6d614a89` | `{"meta": {"n": "<str:24>"}, "target": "<str:21>"}` | principal.department |
| `call-009` | `principal:6d614a89` | `{"meta": {"n": "<str:24>"}, "target": "<str:21>"}` | principal.department |

</details>

---
imported 17, skipped 3 malformed · recorded decisions disagree with base on 1 call (base ref may not be the deployed policy)  
**exit 2** (widening found; --fail-on widen)
