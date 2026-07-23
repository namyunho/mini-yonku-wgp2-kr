-- trace_formation_ppu.lua
-- 포메이션 선택 라벨의 교차 표시를 만드는 PPU 레지스터 쓰기를 추적한다.
-- 포메이션 화면에서 한 항목에 커서를 둔 채 실행하고 4초간 기다린다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/formation_ppu/"
os.execute('mkdir -p "' .. ROOT .. '"')

local trace = assert(io.open(ROOT .. "trace.txt", "w"))
local start_frame = emu.getState()["frameCount"] or 0
local duration = 300

local function hex(value, width)
  return string.format("%0" .. width .. "X", value or 0)
end

local function state_row(tag, extra)
  local st = emu.getState()
  local values = {
    "f=" .. tostring(st["frameCount"] or 0),
    tag,
    "pc=$" .. hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    "main=$" .. hex(st["ppu.mainScreenLayers"], 2),
    "sub=$" .. hex(st["ppu.subScreenLayers"], 2),
    "bg1tm=$" .. hex(st["ppu.layers[0].tilemapAddress"], 4),
    "bg1chr=$" .. hex(st["ppu.layers[0].chrAddress"], 4),
    "bg1h=" .. tostring(st["ppu.layers[0].hscroll"] or 0),
    "bg1v=" .. tostring(st["ppu.layers[0].vscroll"] or 0),
    "bg2tm=$" .. hex(st["ppu.layers[1].tilemapAddress"], 4),
    "bg2chr=$" .. hex(st["ppu.layers[1].chrAddress"], 4),
    "bg2h=" .. tostring(st["ppu.layers[1].hscroll"] or 0),
    "bg2v=" .. tostring(st["ppu.layers[1].vscroll"] or 0),
    "bg3tm=$" .. hex(st["ppu.layers[2].tilemapAddress"], 4),
    "bg3chr=$" .. hex(st["ppu.layers[2].chrAddress"], 4),
    "bg3h=" .. tostring(st["ppu.layers[2].hscroll"] or 0),
    "bg3v=" .. tostring(st["ppu.layers[2].vscroll"] or 0),
    "objbase=$" .. hex(st["ppu.oamBaseAddress"], 4),
    "objmode=" .. tostring(st["ppu.oamMode"] or 0),
    extra or "",
  }
  trace:write(table.concat(values, "\t") .. "\n")
  trace:flush()
end

-- BG/OBJ 베이스, 스크롤, 창, 메인·서브 표시, 색연산 레지스터만 기록한다.
-- VRAM/OAM/CGRAM 데이터 포트는 양이 너무 많으므로 제외한다.
local ranges = {
  {0x2101, 0x2101}, -- OBSEL
  {0x2105, 0x2119}, -- BGMODE..BG4VOFS + VRAM address/data ports
  {0x2123, 0x2133}, -- window/color math/screen mode
}
for _, range in ipairs(ranges) do
  emu.addMemoryCallback(function(address, value)
    local frame = emu.getState()["frameCount"] or 0
    if frame >= start_frame and frame <= start_frame + duration then
      state_row("write", "reg=$" .. hex(address, 4) .. " value=$" .. hex(value, 2))
    end
  end, emu.callbackType.write, range[1], range[2],
      emu.cpuType.snes, emu.memType.snesMemory)
end

emu.addEventCallback(function()
  local frame = emu.getState()["frameCount"] or 0
  if frame < start_frame or frame > start_frame + duration then return end
  state_row("end-frame", "")
  if frame == start_frame + duration then
    trace:close()
    emu.displayMessage("trace", "포메이션 PPU 추적 완료")
  end
end, emu.eventType.endFrame)

state_row("session-start", "")
emu.displayMessage("trace", "커서를 그대로 두고 4초간 기다려 주세요")
