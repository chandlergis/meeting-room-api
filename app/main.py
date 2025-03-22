from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
from typing import List, Dict, Any
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI()

# 从环境变量获取 base_url
BASE_URL = os.getenv("BASE_URL", "http://14.103.250.95:13000")

# 入参模型
class ReservationRequest(BaseModel):
    meeting_title: str
    start_time: str
    end_time: str
    meeting_level: str
    capacity: int
    reserved_by: str

# 出参模型
class Room(BaseModel):
    room_id: int
    room_number: str

class RoomDetail(BaseModel):
    room_id: int
    room_number: str
    capacity: int
    meeting_level: str
    leader_priority: str = None

class ReservationResponse(BaseModel):
    reservation_id: int
    room_id: int
    room_number: str
    start_time: str
    end_time: str
def check_response_status(response: requests.Response) -> None:
    """
    检查 HTTP 响应状态码，处理 PostgREST 返回的 201 等状态码
    """
    if response.status_code not in [200, 201, 204]:
        logger.error(f"请求失败，状态码: {response.status_code}, 响应: {response.text}")
        raise HTTPException(status_code=response.status_code, detail=f"请求失败: {response.text}")
    logger.info(f"请求成功，状态码: {response.status_code}")
# 接口 1：可用会议室查询
@app.post("/api/available-rooms")
async def available_rooms(request: ReservationRequest) -> Dict[str, Any]:
    capacity = request.capacity
    meeting_level = request.meeting_level
    start_time = request.start_time
    end_time = request.end_time

    if not all([capacity, meeting_level, start_time, end_time]):
        return {
            "status": "error",
            "message": "缺少必要参数：capacity, meeting_level, start_time, end_time",
            "data": []
        }

    available_rooms = []
    if meeting_level == "省公司会议":
        # 优先查询专属省公司会议室
        query1 = f"{BASE_URL}/meeting_rooms?capacity=gte.{capacity}&meeting_level=eq.省公司会议（不可兼容总部会议）"
        try:
            response = requests.get(query1)
            response.raise_for_status()
            meeting1_response = response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": f"查询专属会议室失败: {e}", "data": []}

        for room in meeting1_response:
            room_id = room.get("id")
            room_number = room.get("room_number")
            time_query = f"{BASE_URL}/reservations?room_id=eq.{room_id}&start_time=lt.{end_time}&end_time=gt.{start_time}"
            try:
                response = requests.get(time_query)
                response.raise_for_status()
                reservations = response.json()
                if len(reservations) == 0:
                    available_rooms.append({"room_id": room_id, "room_number": room_number})
            except requests.RequestException:
                continue

        # 如果专属会议室不可用，查询兼容会议室
        if not available_rooms:
            query2 = f"{BASE_URL}/meeting_rooms?capacity=gte.{capacity}&meeting_level=like.*可兼容省公司会议*"
            try:
                response = requests.get(query2)
                response.raise_for_status()
                meeting2_response = response.json()
            except requests.RequestException as e:
                return {"status": "error", "message": f"查询兼容会议室失败: {e}", "data": []}

            for room in meeting2_response:
                room_id = room.get("id")
                room_number = room.get("room_number")
                time_query = f"{BASE_URL}/reservations?room_id=eq.{room_id}&start_time=lt.{end_time}&end_time=gt.{start_time}"
                try:
                    response = requests.get(time_query)
                    response.raise_for_status()
                    reservations = response.json()
                    if len(reservations) == 0:
                        available_rooms.append({"room_id": room_id, "room_number": room_number})
                except requests.RequestException:
                    continue

    elif meeting_level == "总部会议":
        query = f"{BASE_URL}/meeting_rooms?capacity=gte.{capacity}&meeting_level=like.*可兼容省公司会议*"
        try:
            response = requests.get(query)
            response.raise_for_status()
            meeting_response = response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": f"查询总部会议室失败: {e}", "data": []}

        for room in meeting_response:
            room_id = room.get("id")
            room_number = room.get("room_number")
            time_query = f"{BASE_URL}/reservations?room_id=eq.{room_id}&start_time=lt.{end_time}&end_time=gt.{start_time}"
            try:
                response = requests.get(time_query)
                response.raise_for_status()
                reservations = response.json()
                if len(reservations) == 0:
                    available_rooms.append({"room_id": room_id, "room_number": room_number})
            except requests.RequestException:
                continue

    else:
        return {"status": "error", "message": "无效的 meeting_level", "data": []}

    return {
        "status": "success",
        "message": "查询成功",
        "data": available_rooms
    }

# 接口 2：可用会议室详情
@app.get("/api/room-details/{room_id}")
async def room_details(room_id: int) -> Dict[str, Any]:
    query = f"{BASE_URL}/meeting_rooms?id=eq.{room_id}"
    try:
        response = requests.get(query)
        response.raise_for_status()
        rooms = response.json()
        if not rooms:
            return {"status": "error", "message": f"会议室 ID {room_id} 不存在", "data": {}}
        room = rooms[0]
        return {
            "status": "success",
            "message": "查询成功",
            "data": {
                "room_id": room.get("id"),
                "room_number": room.get("room_number"),
                "capacity": room.get("capacity"),
                "meeting_level": room.get("meeting_level"),
                "leader_priority": room.get("leader_priority")
            }
        }
    except requests.RequestException as e:
        return {"status": "error", "message": f"查询失败: {e}", "data": {}}

# 接口 3：预定请求
@app.post("/api/reserve")
async def reserve(request: ReservationRequest, room_id: int) -> Dict[str, Any]:
    meeting_title = request.meeting_title
    start_time = request.start_time
    end_time = request.end_time
    reserved_by = request.reserved_by

    if not all([meeting_title, start_time, end_time, reserved_by, room_id]):
        return {
            "status": "error",
            "message": "缺少必要参数：meeting_title, start_time, end_time, reserved_by, room_id",
            "data": {}
        }

    # 查询 room_number
    room_query = f"{BASE_URL}/meeting_rooms?id=eq.{room_id}"
    try:
        response = requests.get(room_query)
        check_response_status(response)
        rooms = response.json()
        if not rooms:
            return {"status": "error", "message": f"会议室 ID {room_id} 不存在", "data": {}}
        room_number = rooms[0].get("room_number")
    except requests.RequestException as e:
        return {"status": "error", "message": f"查询会议室信息失败: {e}", "data": {}}

    # 再次检查时间冲突
    time_query = f"{BASE_URL}/reservations?room_id=eq.{room_id}&start_time=lt.{end_time}&end_time=gt.{start_time}"
    try:
        response = requests.get(time_query)
        check_response_status(response)
        reservations = response.json()
        if len(reservations) > 0:
            return {"status": "error", "message": "会议室在该时间段已被预定", "data": {}}
    except requests.RequestException as e:
        return {"status": "error", "message": f"时间冲突检查失败: {e}", "data": {}}

    # 生成 POST 数据
    post_data = {
        "room_id": room_id,
        "start_time": start_time,
        "end_time": end_time,
        "reserved_by": reserved_by,
        "meeting_title": meeting_title
    }

    # 提交预定请求
    url = f"{BASE_URL}/reservations"
    try:
        response = requests.post(url, json=post_data, headers={"Content-Type": "application/json"})
        check_response_status(response)  # 显式检查 201 状态码
        reservation = response.json()
        return {
            "status": "success",
            "message": f"会议室 {room_number} 预定成功，时间：{start_time}-{end_time}",
            "data": {
                "reservation_id": reservation.get("id", 0),
                "room_id": room_id,
                "room_number": room_number,
                "start_time": start_time,
                "end_time": end_time
            }
        }
    except requests.RequestException as e:
        return {"status": "error", "message": f"预定失败: {e}", "data": {}}

# 接口 4：取消预定
@app.delete("/api/cancel-reservation/{reservation_id}")
async def cancel_reservation(reservation_id: int) -> Dict[str, Any]:
    # 查询预定记录
    query = f"{BASE_URL}/reservations?id=eq.{reservation_id}"
    try:
        response = requests.get(query)
        check_response_status(response)
        reservations = response.json()
        if not reservations:
            return {"status": "error", "message": f"预定 ID {reservation_id} 不存在", "data": {}}
    except requests.RequestException as e:
        return {"status": "error", "message": f"查询预定记录失败: {e}", "data": {}}

    # 删除预定记录
    try:
        response = requests.delete(query)
        check_response_status(response)  # 显式检查 204 或 200 状态码
        return {
            "status": "success",
            "message": f"预定 ID {reservation_id} 已取消",
            "data": {
                "reservation_id": reservation_id
            }
        }
    except requests.RequestException as e:
        return {"status": "error", "message": f"取消预定失败: {e}", "data": {}}