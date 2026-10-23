# -*- coding: utf-8 -*-
"""组合执行型入口的通用骨架：逐步执行、失败即停、逐步报告、可从断点续跑。

返回（打印 + 写 JSON）满足 SKILL.md 的返回契约：outcome / steps / failedAt / done / notDone / next。

用法：把下面 demo() 换成你自己的步骤。每个步骤是一个函数，成功时返回一句「证据」（读回值、数量、路径），
失败时抛异常。步骤之间要传的值放进 ctx（必须能 JSON 序列化），续跑时会从记录里恢复。

    python composite_runner.py            # 跑 demo
    python composite_runner.py --resume   # 从上次失败的步骤接着跑
"""
import json
import os
import sys


class Runner:
    def __init__(self, plan, record_path, ctx, resume=False):
        self.plan, self.record_path, self.ctx, self.steps = plan, record_path, ctx, []
        self.skip = set()
        if resume and os.path.exists(record_path):
            old = json.load(open(record_path, encoding="utf-8"))
            self.skip = set(old.get("done") or [])
            ctx.update(old.get("ctx") or {})

    def run(self, steps):
        """steps: [(名称, 函数), ...]，名称须与 plan 一致。"""
        for name, fn in steps:
            print(f"[{len(self.steps) + 1}/{len(self.plan)}] {name}", flush=True)
            if name in self.skip:
                self.steps.append({"step": name, "status": "完成", "evidence": "上次已完成，续跑跳过"})
                continue
            try:
                ev = fn(self.ctx) or ""
                self.steps.append({"step": name, "status": "完成", "evidence": ev})
                print(f"      完成：{ev}", flush=True)
            except Exception as e:  # 任何失败都停下，并如实记录
                self.steps.append({"step": name, "status": "失败", "error": f"{type(e).__name__}: {e}"})
                print(f"      失败：{e}", flush=True)
                break
        return self.finish()

    def finish(self):
        done = [s["step"] for s in self.steps if s["status"] == "完成"]
        failed = next((s for s in self.steps if s["status"] == "失败"), None)
        r = {"outcome": "Failure" if failed else "Success",
             "failedAt": failed and failed["step"], "error": failed and failed["error"],
             "done": done, "notDone": self.plan[len(self.steps):], "steps": self.steps, "ctx": self.ctx,
             "next": ("修好后加 --resume 从「%s」接着跑" % failed["step"]) if failed else "无"}
        with open(self.record_path, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        print("\n结果：" + (f"失败，停在「{r['failedAt']}」" if failed else "全部完成"))
        print("做完：" + ("、".join(done) or "无"))
        print("没做：" + ("、".join(r["notDone"]) or "无"))
        return 1 if failed else 0


def demo(resume):
    plan = ["准备", "处理", "核对"]
    flag = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".demo_fail_once")

    def prepare(ctx):
        ctx["items"] = 3
        return "准备了 3 项"

    def process(ctx):
        if not os.path.exists(flag):          # 第一次故意失败，演示「停在哪、做完什么、没做什么」和续跑
            open(flag, "w").close()
            raise RuntimeError("演示用的失败：再加 --resume 跑一次")
        os.remove(flag)
        return f"处理了 {ctx['items']} 项"

    def verify(ctx):
        return "读回 3 项，一致"

    R = Runner(plan, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".demo_record.json"), {}, resume)
    return R.run(list(zip(plan, [prepare, process, verify])))


if __name__ == "__main__":
    sys.exit(demo("--resume" in sys.argv))
