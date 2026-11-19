"""Local multi-store configuration editor; does not log in or publish."""
import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

CONFIG = Path(__file__).with_name('config.json')


def main():
    root = tk.Tk()
    root.title('亚马逊流水线 · 店铺配置')
    root.geometry('640x610')
    panel = ttk.Frame(root, padding=20)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='钧飞ERP · 多店铺配置', font=('Microsoft YaHei', 15)).pack(anchor='w')
    ttk.Label(panel, text='每个店铺/站点独立保存。修改仅影响新任务，不提交商品。').pack(anchor='w', pady=8)
    generation_enabled = tk.BooleanVar(value=bool(json.loads(CONFIG.read_text(encoding='utf-8')).get('images', {}).get('enabled', False)))
    ttk.Checkbutton(panel, text='启用AI生图（必须设置每款与每日预算）', variable=generation_enabled).pack(anchor='w', pady=4)
    variables = {}
    labels = [('name', '配置档案名'), ('store', '钧飞ERP实际店铺名'), ('marketplace', '站点代码（US / UK等）'),
              ('shipping_template', '实际运费模板'), ('quantity', '每子变体库存'), ('mode', '模式（draft草稿 / publish发布）'),
              ('per_product_budget_rmb', '每款生图预算（人民币）'), ('daily_budget_rmb', '每日生图预算（人民币）')]
    cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
    choices = ttk.Combobox(panel, values=list(cfg.get('profiles', {})), state='normal')
    choices.pack(fill='x', pady=6)
    choices.set(cfg.get('defaults', {}).get('profile', ''))
    for key, label in labels:
        row = ttk.Frame(panel); row.pack(fill='x', pady=6)
        ttk.Label(row, text=label, width=32).pack(side='left')
        variables[key] = tk.StringVar()
        if key == 'mode':
            widget = ttk.Combobox(row, textvariable=variables[key], values=['draft', 'publish'], state='readonly')
        else:
            widget = ttk.Entry(row, textvariable=variables[key])
        widget.pack(side='right', fill='x', expand=True)

    def load(_=None):
        current = json.loads(CONFIG.read_text(encoding='utf-8'))
        name = choices.get()
        profile = current.get('profiles', {}).get(name, {})
        for key, _label in labels:
            value = name if key == 'name' else current['images'].get(key, '') if key.endswith('_budget_rmb') else profile.get(key, current['publishing'].get(key, ''))
            variables[key].set('' if value is None else str(value))

    def save():
        try:
            current = json.loads(CONFIG.read_text(encoding='utf-8'))
            values = {key: var.get().strip() for key, var in variables.items()}
            if any(not values[k] for k in ('name', 'store', 'marketplace', 'shipping_template')):
                raise ValueError('请填写档案名、实际店铺名、站点和运费模板')
            quantity = int(values['quantity'])
            if quantity < 0: raise ValueError('库存不得为负')
            for key in ('per_product_budget_rmb', 'daily_budget_rmb'):
                amount = float(values[key]) if values[key] else None
                if amount is not None and not 0 <= amount < float('inf'):
                    raise ValueError('预算须为正数，留空表示待定')
                current['images'][key] = amount
            if generation_enabled.get() and any(current['images'][key] is None for key in ('per_product_budget_rmb', 'daily_budget_rmb')):
                raise ValueError('启用生图前必须填写每款与每日预算')
            current['images']['enabled'] = generation_enabled.get()
            current.setdefault('profiles', {})[values['name']] = {
                'platform': 'junfei', 'store': values['store'], 'marketplace': values['marketplace'].upper(),
                'shipping_template': values['shipping_template'], 'quantity': quantity, 'mode': values['mode']}
            temp = CONFIG.with_suffix('.tmp')
            temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(CONFIG)
            choices['values'] = list(current['profiles'])
            choices.set(values['name'])
            messagebox.showinfo('已保存', '店铺档案和图片设置已保存；默认档案需在 config.json 的 defaults.profile 中设置。')
        except (ValueError, OSError) as exc:
            messagebox.showerror('未保存', str(exc))

    choices.bind('<<ComboboxSelected>>', load)
    choices.bind('<Return>', load)
    load()
    ttk.Button(panel, text='保存店铺档案及预算', command=save).pack(pady=14)
    ttk.Label(panel, text='预算尚未连接费用扣减执行器。发布模式仍要求实际页面适配与授权。', wraplength=560).pack(anchor='w')
    ttk.Label(panel, text='默认档案可在 config.json 的 defaults.profile 设置；选择档案不会改默认值。', wraplength=560).pack(anchor='w', pady=6)
    root.mainloop()


if __name__ == '__main__':
    main()
