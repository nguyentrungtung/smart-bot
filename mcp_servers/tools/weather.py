import logging
import httpx
from pydantic import BaseModel, Field
import mcp.types as types

logger = logging.getLogger("mcp_server.weather")

class WeatherParams(BaseModel):
    location: str = Field(description="Tên thành phố/tỉnh (ví dụ: 'Hanoi', 'Ho Chi Minh')")
    unit: str = Field(default="C", description="Đơn vị nhiệt độ (C hoặc F)")

async def get_weather(arguments: dict) -> list[types.TextContent]:
    """Lấy thông tin thời tiết THỜI GIAN THỰC."""
    location = arguments.get("location", "Hanoi")
    unit = arguments.get("unit", "C")
    
    logger.info(f"--- [TOOL CALL] get_weather start: location={location} ---")
    
    async with httpx.AsyncClient() as client:
        try:
            # Bước 1: Geocoding
            logger.info(f"Step 1: Geocoding for {location}...")
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=vi&format=json"
            geo_response = await client.get(geo_url, timeout=10.0)
            geo_data = geo_response.json()
            
            if not geo_data.get("results"):
                err_msg = f"Không tìm thấy vị trí địa lý cho: {location}"
                logger.warning(err_msg)
                return [types.TextContent(type="text", text=err_msg)]
            
            res = geo_data["results"][0]
            lat, lon = res["latitude"], res["longitude"]
            loc_full_name = res.get("name", location)
            country = res.get("country", "")
            
            # Bước 2: Weather Data
            logger.info(f"Step 2: Fetching weather for {loc_full_name} ({lat}, {lon})")
            unit_param = "celsius" if unit.upper() == "C" else "fahrenheit"
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&temperature_unit={unit_param}"
            
            w_resp = await client.get(weather_url, timeout=10.0)
            w_resp.raise_for_status()
            w_data = w_resp.json()
            
            current = w_data.get("current_weather", {})
            if current:
                temp = current.get("temperature")
                wind = current.get("windspeed")
                time_str = current.get("time")
                result_text = (
                    f"Thời tiết hiện tại ở {loc_full_name} ({country}):\n"
                    f"- Nhiệt độ: {temp}°{unit.upper()}\n"
                    f"- Tốc độ gió: {wind} km/h\n"
                    f"- Cập nhật lúc: {time_str} (UTC)\n"
                    f"Dữ liệu được cung cấp bởi Open-Meteo."
                )
                logger.info(f"--- [TOOL SUCCESS] get_weather completed for {location} ---")
                return [types.TextContent(type="text", text=result_text)]
            else:
                return [types.TextContent(type="text", text=f"Không thể lấy thông tin chi tiết thời tiết cho {location}.")]
                
        except Exception as e:
            err_msg = f"Lỗi truy vấn thời tiết cho {location}: {str(e)}"
            logger.error(err_msg)
            return [types.TextContent(type="text", text=err_msg)]
