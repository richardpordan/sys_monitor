'''NiceGUI Python System Monitor'''


import asyncio
import psutil
import datetime
import pandas as pd
from nicegui import app, ui


# System Monitor Backend
class SysMonitorEngine:
  def __init__(self, n_obs):
    self.cpu_info = pd.DataFrame()
    self.cpu_high = None
    self.cpu_critical = None
    self.gpu_info = pd.DataFrame()
    self.ram_total = None
    self.ram_info = pd.DataFrame()
    self.net_info = pd.DataFrame()
    self.n_obs = n_obs

  async def timestamp(self):
    return str(datetime.datetime.now())

  def round2(self, num: float|int):
    return round(num / (1024**2), 2)

  async def update_net(self, first_run: bool = False):
    # net_stats = psutil.net_io_counters()
    pass

  async def update_memory(self, first_run: bool = False):
    mem_query = psutil.virtual_memory()
    mem_stats = {}
    mem_stats["timestamp"] = await self.timestamp()
    mem_stats["percent [%]"] = mem_query.percent
    mem_stats["available [MiB]"] = self.round2(mem_query.available)
    mem_stats["used [MiB]"] = self.round2(mem_query.used)
    
    if first_run:
      self.ram_total = self.round2(mem_query.total)

    self.ram_info = pd.concat(
      [
        self.ram_info,
        pd.DataFrame.from_records([mem_stats])
      ],
    ).tail(self.n_obs).reset_index(drop=True)

  async def update_cpu_info(self, first_run: bool = False):
    """Update CPU info"""
    info = {}
    info["timestamp"] = await self.timestamp()
    
    core_temps = psutil.sensors_temperatures()['coretemp']

    if first_run:
      self.cpu_high = core_temps[0].high
      self.cpu_critical = core_temps[0].critical
    
    info["cpu_percent"] = psutil.cpu_percent(interval=1)
    for core in core_temps:
      info[core.label] = core.current
    
    self.cpu_info = pd.concat(
      [
        self.cpu_info,
        pd.DataFrame.from_records([info])
      ],
    ).tail(self.n_obs).reset_index(drop=True)

  async def update_gpu_info(self, first_run: bool = False):
    gpu_data_cols = [
      "timestamp",
      "name",
      "pstate", 
      "temperature.gpu", 
      "utilization.gpu", 
      "utilization.memory", 
      "power.draw", 
      "enforced.power.limit",
    ]

    proc = await asyncio.create_subprocess_exec(
      "nvidia-smi",
      f"--query-gpu={','.join(gpu_data_cols)}", 
      "--format=csv,nounits",
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    
    if not stderr:
      dcd_stdout = stdout.decode("utf-8")
      output = [
        tuple(el.split(", ")) for el in dcd_stdout.split("\n")[:2]
      ]
    
      if first_run:
        self.gpu_info = pd.DataFrame(columns=output[0])
    
      self.gpu_info.loc[len(self.gpu_info)] = output[1]
      self.gpu_info = self.gpu_info.tail(self.n_obs).reset_index(drop=True)
    
  async def update(self, first_run: bool = False):
    await self.update_cpu_info(first_run=first_run)
    await self.update_gpu_info(first_run=first_run)
    await self.update_memory(first_run=first_run)


# System Monitor Web App Setup
class SysMonitor:
  def __init__(self, n_obs: int = 59, update_interval: int = 5):
    self.engine = None
    self.n_obs = n_obs
    self.update_interval = update_interval
    self.current_table_data = pd.DataFrame()
    self.current_selection = "cpu"

  async def plot_chart(self, measure: str):
    if measure == "cpu":
      data = self.engine.cpu_info.cpu_percent.to_list()
    if measure == "cpu_temp":
      data = self.engine.cpu_info['Package id 0'].to_list()
    if measure == "memory":
      data = self.engine.ram_info['percent [%]'].to_list()
    if measure == "gpu":
      data = self.engine.gpu_info['utilization.gpu [%]'].to_list()
    chart = ui.echart({
      'xAxis': {'type': 'category'},
      # 'yAxis': {'axisLabel': {':formatter': f'value => "%" + value'}},
      'yAxis': {'axisLabel': {':formatter': 'value => value'}},
      'series': [{
        'type': 'line', 
        'data': data,
        'lineStyle': {
          'normal': {
            'color': '#39FF14',
            'width': 3,
            'type':'solid'
          }
        },
        'itemStyle': {
          'normal': {
            'color': '#39FF14',
            'width': 3,
            'type':'solid'
          }
        }
      }],
    })

    return chart.classes('chart')

  async def update_table_data(self, measure: str):
    if measure == "cpu":
      self.current_table_data = self.engine.cpu_info
    if measure == "mem":
      self.current_table_data = self.engine.ram_info
    if measure == "gpu":
      self.current_table_data = self.engine.gpu_info

  async def change_table(self, measure: str):
    self.current_selection = measure
    await self.refresh()

  @ui.refreshable
  async def main_frontend(self):
    """Updateable portion of the UI"""    
    with ui.element("div").props("id=container"):

      with ui.element("div").classes("triple-row"):

        with ui.element("div").props("class=panel id=cpu-panel").on(
              'click', lambda: self.change_table("cpu")
            ):
          ui.html("<h2>CPU Utilization (%)</h2>")
          await self.plot_chart("cpu")

        with ui.element("div").props("class=panel id=cpu-temp-panel").on(
              'click', lambda: self.change_table("cpu")
            ):
          ui.html("<h2>CPU Temperature (°C)</h2>")
          await self.plot_chart("cpu_temp")

        with ui.element("div").props("class=panel id=mem-panel").on(
              'click', lambda: self.change_table("mem")
            ):
          ui.html("<h2>Memory (used %)</h2>")
          await self.plot_chart("memory")
          
        with ui.element("div").props("class=panel id=gpu-panel").on(
              'click', lambda: self.change_table("gpu")
            ):
          ui.html("<h2>GPU Utilization (%)</h2>")
          await self.plot_chart("gpu")
          
      with ui.element("div").classes("single-row"):

        with ui.element("div").props("class=panel id=panel4"):
          ui.html(
            f"<h2>Selected detail: {self.current_selection.upper()}</h2>"
          )
          ui.table(
            rows=self.current_table_data.to_dict('records'), 
            pagination={
              'rowsPerPage': 5, 
              'sortBy': 'timestamp', 
              'descending': True,
              'page': 1}
          )
          
  async def refresh(self):
    await self.update_table_data(self.current_selection)
    self.main_frontend.refresh()

  async def run(self):
    """Run app"""
    # Read in custom css from static and pictures from assets.
    app.add_static_files('/static', 'static')
    ui.add_head_html(
      "<style>" + open("static/styles.css", "r").read() + "</style>"
    )
    ui.dark_mode().enable()
    
    # Basic UI
    with ui.element("header"):
      ui.html("<h1>System Monitor</h1>")
    
    blinker = ui.html("<div class='text blink-yellow'>Loading...</div>")

    # Fire up the backend
    self.engine = SysMonitorEngine(n_obs=self.n_obs)

    # Get initial data
    await self.engine.update(first_run=True)
    self.current_table_data = self.engine.cpu_info
    blinker.delete()
    await self.main_frontend()
    await asyncio.sleep(self.update_interval)
    
    # Continue stream data
    while True:
      await self.engine.update()
      await self.refresh()
      await asyncio.sleep(self.update_interval)


# Main Guard (NiceGUI requires __mp_main__ as well.)
if __name__ in {"__main__", "__mp_main__"}:
  sys_monitor = SysMonitor()
  app.on_startup(sys_monitor.run)
  ui.run(tailwind=False)
  # ui.run(reload=False, tailwind=False)
