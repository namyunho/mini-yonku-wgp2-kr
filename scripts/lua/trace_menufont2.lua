-- trace_menufont2.lua : 메뉴 진입까지 모든 LZSS 디컴프 소스 로깅 + 메뉴렌더 시 VRAM 덤프.
--   디컴프레서 $C0:0D91: 소스 롱포인터 $11-$13, 길이 $05. 출력은 항상 $7F:1000.
--   → 로그된 소스를 오프라인 디컴프해 폰트(VRAM chr=0) 매칭. 입력주입 없음(사용자 조작).
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/"
os.execute('mkdir "C:\\Users\\namyunho\\mini-yonku-wgp2-kr\\tmp\\trace\\menu2" 2>nul')
local decs = {}
emu.addMemoryCallback(function()
  local st = emu.getState()
  local d = st["cpu.d"]
  local function r(a) return emu.read(d + a, emu.memType.snesWorkRam) end
  local lo, mi, bk = r(0x11), r(0x12), r(0x13)
  local len = r(0x05) + r(0x06) * 256
  decs[#decs+1] = string.format("f=%-6d src=$%02X:%04X len=%d", st["frameCount"], bk, mi*256+lo, len)
  -- 즉시 flush (덤프 전 크래시 대비)
  local f = io.open(ROOT .. "decomp_log.txt", "w")
  for _, s in ipairs(decs) do f:write(s .. "\n") end
  f:close()
end, emu.callbackType.exec, 0xC00D91, 0xC00D91, emu.cpuType.snes, emu.memType.snesMemory)

local pending = nil
local dumps = 0
emu.addMemoryCallback(function()
  if not pending then pending = emu.getState()["frameCount"] + 2 end
end, emu.callbackType.read, 0xC071B9, 0xC07210, emu.cpuType.snes, emu.memType.snesMemory)

local function dumpMem(name, mt, sz)
  local f = io.open(ROOT .. name, "wb"); if not f then return end
  local t = {}
  for i = 0, sz - 1 do t[#t+1] = string.char(emu.read(i, mt) & 0xFF); if #t == 4096 then f:write(table.concat(t)); t = {} end end
  if #t > 0 then f:write(table.concat(t)) end; f:close()
end
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  if pending and fr >= pending then
    dumps = dumps + 1
    dumpMem("vram.bin", emu.memType.snesVideoRam, 0x10000)
    dumpMem("cgram.bin", emu.memType.snesCgRam, 0x200)
    local st = emu.getState()
    local f = io.open(ROOT .. "ppu.txt", "w")
    f:write(string.format("dump#%d frame=%d bgMode=%s\n", dumps, fr, tostring(st["ppu.bgMode"])))
    for L = 1, 4 do local p = "ppu.layers[" .. (L-1) .. "]."
      f:write(string.format("BG%d tilemap=%s chr=%s\n", L, tostring(st[p.."tilemapAddress"]), tostring(st[p.."chrAddress"]))) end
    f:close()
    emu.displayMessage("dump", "menu dumped #" .. dumps .. " @f" .. fr)
    pending = nil
  end
end, emu.eventType.endFrame)
