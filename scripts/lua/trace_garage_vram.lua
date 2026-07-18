-- trace_garage_vram.lua : 개러지 화면에서 VRAM 타일 700~1100 영역에 쓰는 DMA를 전수 로깅.
--   목적: 한글 영역(VRAM 타일 800~)을 무엇이 덮어쓰는지(경합) 규명 → 안전 VRAM 재배치.
--   사용: Mesen(맥)으로 out/wgp2_kr.smc 로드 → 이 스크립트 실행 → 개러지 진입 → 잠시 대기 → 종료.
--   출력: 아래 OUT 경로. (Mesen 설정: ScriptWindow.AllowIoOsAccess=true 필요)
local OUT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/garage_vram.txt"
local rows = {}
local injectRan = 0
local seen = {}   -- 중복 억제(같은 tile범위+PC)

local function flush()
  local f = io.open(OUT, "w")
  if not f then return end
  f:write("한글인젝트 $C1:9940 exec = " .. injectRan .. "\n")
  f:write("VRAM 타일 700~1100 영역 DMA 기록:\n")
  for _, s in ipairs(rows) do f:write(s .. "\n") end
  f:close()
end

-- 한글 인젝트 루틴 실행 카운트
emu.addMemoryCallback(function()
  injectRan = injectRan + 1; flush()
end, emu.callbackType.exec, 0xC19940, 0xC19940, emu.cpuType.snes, emu.memType.snesMemory)

-- DMA 트리거($420B) → VRAM 대상 채널 중 타일 700~1100 겹치면 로깅
emu.addMemoryCallback(function(addr, value)
  local st = emu.getState()
  local vmadd = st["ppu.vramAddress"] or 0
  local pc = st["cpu.pc"] or 0
  local pb = st["cpu.k"] or 0
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local dest = st[p .. "destAddress"]
      if dest == 0x18 or dest == 0x19 then
        local sb = st[p .. "srcBank"] or 0
        local sa = st[p .. "srcAddress"] or 0
        local size = st[p .. "transferSize"] or 0
        if size == 0 then size = 65536 end
        local vt = vmadd // 8
        local endt = vt + size // 16
        if endt >= 700 and vt <= 1100 then
          local key = string.format("%d-%d@%02X%04X", vt, endt, pb, pc)
          if not seen[key] then
            seen[key] = true
            rows[#rows+1] = string.format("f=%d PC=$%02X:%04X ch%d VRAMtile %d-%d src=$%02X:%04X size=%d",
              st["frameCount"] or 0, pb, pc, ch, vt, endt, sb, sa, size)
            flush()
          end
        end
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B, emu.cpuType.snes, emu.memType.snesMemory)

emu.displayMessage("trace", "garage VRAM trace armed")
