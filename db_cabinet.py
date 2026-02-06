from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pyodbc

from logger_utils import get_logger


log = get_logger(__name__)


@dataclass
class DoorStatus:
    """Unified door/slot status."""

    cabinet_type: str  # 'cupboard' or 'disshoegoods'
    cabinet_key: str
    cabinet_name: str

    door_no: int
    door_name: str

    user_id: Optional[str]
    user_name: Optional[str]

    # Optional fields for extra detail
    last_update_time: Optional[str] = None
    reserved_mark: Optional[int] = None
    ending: Optional[int] = None
    lock_state: Optional[int] = None
    lock_name: Optional[str] = None
    size_name: Optional[str] = None
    style_name: Optional[str] = None
    device_name: Optional[str] = None  # DisShoeGoods -> Device.Name

    # DisShoeGoods addressing (one device can have multiple address groups)
    device_id: Optional[str] = None
    address: Optional[int] = None

    # DisShoeGoods extra
    # Whether the slot contains slippers/shoes (may have no bound user)
    has_item: bool = False
    amount: Optional[int] = None

    # Box-based fixed/cycle status (optional)
    fixed_user_name: Optional[str] = None
    is_cycle: Optional[bool] = None


class CabinetDB:
    """Data access for cabinet status panels."""

    def __init__(self, conn_str: str):
        self.conn_str = conn_str

    def _conn(self):
        return pyodbc.connect(self.conn_str, autocommit=False)

    # -------------------------
    # Cupboard / Box (更衣柜/更鞋柜)
    # -------------------------
    def list_cupboards(self) -> List[Tuple[str, str]]:
        """Return [(cupboard_id, display_name), ...]."""
        sql = """
        SELECT
          c.CupboardId,
          c.No AS CupboardNo,
          c.Sex,
          c.BoxCount,
          a.Name AS AreaName
        FROM OperRoom.dbo.Cupboard c
        JOIN OperRoom.dbo.Area a
          ON c.AreaDeviceId = a.AreaDeviceId
         AND c.Sex = a.Sex
        ORDER BY a.Name, c.Sex, c.No
        """
        out: List[Tuple[str, str]] = []
        with self._conn() as conn:
            rows = conn.cursor().execute(sql).fetchall()
        for r in rows:
            cid = str(r[0])
            cno = int(r[1] or 0)
            sex = int(r[2] or 0)
            cnt = int(r[3] or 0)
            area = str(r[4] or "")
            sex_name = "男" if sex == 1 else ("女" if sex == 0 or sex == 2 else f"Sex{sex}")
            out.append((cid, f"{sex_name}{area} {cno}号柜({cnt}门)"))
        return out

    def list_doors_by_cupboard(self, cupboard_id: str) -> List[DoorStatus]:
        sql = """
        SELECT
          c.CupboardId,
          c.No AS CupboardNo,
          c.Sex,
          c.BoxCount,
          a.Name AS AreaName,
          b.No AS BoxNo,
          b.BoxShowName,
          b.UserId,
          u.Name AS UserName,
          b.LastUpdateTime,
          b.ReservedMark,
          b.Ending
        FROM OperRoom.dbo.Box b
        JOIN OperRoom.dbo.Cupboard c
          ON b.CupboardId = c.CupboardId
        JOIN OperRoom.dbo.Area a
          ON c.AreaDeviceId = a.AreaDeviceId
         AND c.Sex = a.Sex
        LEFT JOIN OperRoom.dbo.[User] u
          ON b.UserId = u.UserId
        WHERE c.CupboardId = ?
        ORDER BY b.No
        """
        res: List[DoorStatus] = []
        with self._conn() as conn:
            rows = conn.cursor().execute(sql, cupboard_id).fetchall()
        for r in rows:
            cid = str(r[0])
            cno = int(r[1] or 0)
            sex = int(r[2] or 0)
            # boxcount = int(r[3] or 0)
            area = str(r[4] or "")
            box_no = int(r[5] or 0)
            show = str(r[6] or str(box_no))
            uid = str(r[7]) if r[7] is not None else None
            uname = str(r[8]) if r[8] is not None else None
            last = str(r[9]) if r[9] is not None else None
            rsv = int(r[10]) if r[10] is not None else None
            ending = int(r[11]) if r[11] is not None else None
            sex_name = "男" if sex == 1 else ("女" if sex == 0 or sex == 2 else f"Sex{sex}")
            cab_name = f"{sex_name}{area} {cno}号柜"
            res.append(
                DoorStatus(
                    cabinet_type="cupboard",
                    cabinet_key=cid,
                    cabinet_name=cab_name,
                    door_no=box_no,
                    door_name=show,
                    user_id=uid,
                    user_name=uname,
                    last_update_time=last,
                    reserved_mark=rsv,
                    ending=ending,
                )
            )
        return res

    def list_doors_by_cupboard_nos(self, cupboard_nos: List[int]) -> List[DoorStatus]:
        """Return doors for multiple cupboards by c.No."""
        if not cupboard_nos:
            return []
        placeholders = ",".join(["?"] * len(cupboard_nos))
        sql = f"""
        SELECT
          c.CupboardId,
          c.No AS CupboardNo,
          c.Sex,
          c.BoxCount,
          a.Name AS AreaName,
          b.No AS BoxNo,
          b.BoxShowName,
          b.UserId,
          u.Name AS UserName,
          b.LastUpdateTime,
          b.ReservedMark,
          b.Ending
        FROM OperRoom.dbo.Box b
        JOIN OperRoom.dbo.Cupboard c
          ON b.CupboardId = c.CupboardId
        JOIN OperRoom.dbo.Area a
          ON c.AreaDeviceId = a.AreaDeviceId
         AND c.Sex = a.Sex
        LEFT JOIN OperRoom.dbo.[User] u
          ON b.UserId = u.UserId
        WHERE c.No IN ({placeholders})
        ORDER BY c.No, b.No
        """
        res: List[DoorStatus] = []
        with self._conn() as conn:
            rows = conn.cursor().execute(sql, *cupboard_nos).fetchall()
        for r in rows:
            cid = str(r[0])
            cno = int(r[1] or 0)
            sex = int(r[2] or 0)
            area = str(r[4] or "")
            box_no = int(r[5] or 0)
            show = str(r[6] or str(box_no))
            uid = str(r[7]) if r[7] is not None else None
            uname = str(r[8]) if r[8] is not None else None
            last = str(r[9]) if r[9] is not None else None
            rsv = int(r[10]) if r[10] is not None else None
            ending = int(r[11]) if r[11] is not None else None
            sex_name = "男" if sex == 1 else ("女" if sex == 0 or sex == 2 else f"Sex{sex}")
            cab_name = f"{sex_name}{area} {cno}号柜"
            door_label = f"{cno}-{box_no:02d}"
            res.append(
                DoorStatus(
                    cabinet_type="cupboard",
                    cabinet_key=cid,
                    cabinet_name=cab_name,
                    door_no=box_no,
                    door_name=door_label if show == str(box_no) else f"{cno}-{show}",
                    user_id=uid,
                    user_name=uname,
                    last_update_time=last,
                    reserved_mark=rsv,
                    ending=ending,
                )
            )
        return res

    def list_box_users_by_cupboard_no(self, cupboard_no: int) -> List[Tuple[int, Optional[str]]]:
        """Return [(box_no, user_name), ...] for a cupboard number (c.No)."""
        sql = """
        SELECT
          b.No AS BoxNo,
          u.Name AS UserName
        FROM OperRoom.dbo.Box b
        JOIN OperRoom.dbo.Cupboard c
          ON b.CupboardId = c.CupboardId
        LEFT JOIN OperRoom.dbo.[User] u
          ON b.UserId = u.UserId
        WHERE c.No = ?
        ORDER BY b.No
        """
        with self._conn() as conn:
            rows = conn.cursor().execute(sql, cupboard_no).fetchall()
        out: List[Tuple[int, Optional[str]]] = []
        for r in rows:
            box_no = int(r[0] or 0)
            uname = str(r[1]) if r[1] is not None else None
            out.append((box_no, uname))
        return out

    def list_user_names_by_ids(self, user_ids: List[str]) -> List[Tuple[str, Optional[str]]]:
        """Return [(user_id, user_name), ...] for given user ids."""
        if not user_ids:
            return []
        placeholders = ",".join(["?"] * len(user_ids))
        sql = f"""
        SELECT u.UserId, u.Name
        FROM OperRoom.dbo.[User] u
        WHERE u.UserId IN ({placeholders})
        """
        with self._conn() as conn:
            rows = conn.cursor().execute(sql, *user_ids).fetchall()
        out: List[Tuple[str, Optional[str]]] = []
        for r in rows:
            uid = str(r[0])
            uname = str(r[1]) if r[1] is not None else None
            out.append((uid, uname))
        return out

    def list_users_by_sex(self, sex: int) -> List[Tuple[str, str, Optional[str]]]:
        """Return [(user_id, user_name, login_name), ...] filtered by sex (1=male, 0=female)."""
        sql = """
        SELECT u.UserId, u.Name, u.LoginName
        FROM OperRoom.dbo.[User] u
        WHERE u.Sex = ?
        ORDER BY u.Name
        """
        with self._conn() as conn:
            rows = conn.cursor().execute(sql, sex).fetchall()
        out: List[Tuple[str, str, Optional[str]]] = []
        for r in rows:
            uid = str(r[0])
            uname = str(r[1]) if r[1] is not None else ""
            login = str(r[2]) if r[2] is not None else None
            out.append((uid, uname, login))
        return out

    # -------------------------
    # DisShoeGoods (发鞋柜)
    # -------------------------
    def list_disshoe_cabinets(self) -> List[Tuple[str, str]]:
        """Return [("DeviceId|Address", display_name), ...]."""
        sql = """
        SELECT DISTINCT DeviceId, Address
        FROM OperRoom.dbo.DisShoeGoods
        ORDER BY DeviceId, Address
        """
        out: List[Tuple[str, str]] = []
        with self._conn() as conn:
            rows = conn.cursor().execute(sql).fetchall()
        for r in rows:
            dev = str(r[0])
            addr = str(r[1])
            key = f"{dev}|{addr}"
            out.append((key, f"发鞋柜 Dev{dev} Addr{addr}"))
        return out

    def list_disshoe_doors_all(self, device_ids: Optional[List[str]] = None) -> List[DoorStatus]:
        """Return all DisShoeGoods doors, optionally filtered by device_ids.

        This is used for the "show all" shoe-cabinet view.
        """
        # Shoe cabinets are defined in OperRoom.dbo.Device, e.g. "男发鞋柜" / "女发鞋柜".
        # Filter by DeviceType=100 and Name contains "发鞋柜" to avoid showing unrelated devices.
        where_parts = ["dv.DeviceType = 100", "dv.Name LIKE N'%发鞋柜%'"]
        params: list = []
        if device_ids:
            placeholders = ",".join(["?"] * len(device_ids))
            where_parts.append(f"dsg.DeviceId IN ({placeholders})")
            params.extend(device_ids)
        where = "WHERE " + " AND ".join(where_parts)

        sql = f"""
        SELECT
          dsg.DeviceId,
          dsg.Address,
          dsg.BoxNo,
          dsg.Amount,
          dsg.RFIDMsg,
          dsg.State,
          CASE dsg.State WHEN 10 THEN N'未锁定'
                         WHEN 20 THEN N'锁定'
                         ELSE N'未知' END AS StateName,
          s.Name  AS SizeName,
          sl.Name AS StyleName,
          dsg.UserId,
          u.Name AS UserName,
          dv.Name AS DeviceName
        FROM OperRoom.dbo.DisShoeGoods dsg
        JOIN OperRoom.dbo.Device dv ON dv.DeviceId = dsg.DeviceId
        LEFT JOIN OperRoom.dbo.[Size]  s  ON dsg.SizeId = s.SizeId
        LEFT JOIN OperRoom.dbo.[Style] sl ON s.StyleId  = sl.StyleId
        LEFT JOIN OperRoom.dbo.[User]  u  ON dsg.UserId = u.UserId
        {where}
        ORDER BY dsg.DeviceId, dsg.Address, dsg.BoxNo
        """

        res: List[DoorStatus] = []
        with self._conn() as conn:
            rows = conn.cursor().execute(sql, *params).fetchall()

        for r in rows:
            dev = str(r[0])
            addr = str(r[1])
            box_no = int(r[2] or 0)
            amt = int(r[3]) if r[3] is not None else None
            rfid = str(r[4]) if r[4] is not None else None
            st = int(r[5]) if r[5] is not None else None
            st_name = str(r[6] or "")
            size_name = str(r[7]) if r[7] is not None else None
            style_name = str(r[8]) if r[8] is not None else None
            uid = str(r[9]) if r[9] is not None else None
            uname = str(r[10]) if r[10] is not None else None
            dev_name = str(r[11]) if r[11] is not None else None

            # Determine if there is an item in the slot.
            has_item = False
            if amt is not None and amt > 0:
                has_item = True
            if size_name or style_name or rfid:
                has_item = True

            cab_key = f"{dev}|{addr}"
            cab_name = f"发鞋柜 Dev{dev} Addr{addr}"
            res.append(
                DoorStatus(
                    cabinet_type="disshoegoods",
                    cabinet_key=cab_key,
                    cabinet_name=cab_name,
                    device_id=str(dev),
                    address=int(addr) if str(addr).isdigit() else None,
                    door_no=box_no,
                    door_name=str(box_no),
                    user_id=uid,
                    user_name=uname,
                    lock_state=st,
                    lock_name=st_name,
                    size_name=size_name,
                    style_name=style_name,
                    device_name=dev_name,
                    has_item=has_item,
                    amount=amt,
                )
            )
        return res

    def list_doors_by_disshoe(self, device_id: str, address: str) -> List[DoorStatus]:
        # Use left joins to avoid dropping rows when SizeId/StyleId is NULL.
        sql = """
        SELECT
          dsg.DeviceId,
          dsg.Address,
          dsg.BoxNo,
          dsg.State,
          CASE dsg.State WHEN 10 THEN N'未锁定'
                         WHEN 20 THEN N'锁定'
                         ELSE N'未知' END AS StateName,
          s.Name  AS SizeName,
          sl.Name AS StyleName,
          dsg.UserId,
          u.Name AS UserName
        FROM OperRoom.dbo.DisShoeGoods dsg
        LEFT JOIN OperRoom.dbo.[Size]  s  ON dsg.SizeId = s.SizeId
        LEFT JOIN OperRoom.dbo.[Style] sl ON s.StyleId  = sl.StyleId
        LEFT JOIN OperRoom.dbo.[User]  u  ON dsg.UserId = u.UserId
        WHERE dsg.DeviceId = ? AND dsg.Address = ?
        ORDER BY dsg.BoxNo
        """
        res: List[DoorStatus] = []
        with self._conn() as conn:
            rows = conn.cursor().execute(sql, device_id, address).fetchall()

        cab_key = f"{device_id}|{address}"
        cab_name = f"发鞋柜 Dev{device_id} Addr{address}"
        for r in rows:
            box_no = int(r[2] or 0)
            st = int(r[3]) if r[3] is not None else None
            st_name = str(r[4] or "")
            size_name = str(r[5]) if r[5] is not None else None
            style_name = str(r[6]) if r[6] is not None else None
            uid = str(r[7]) if r[7] is not None else None
            uname = str(r[8]) if r[8] is not None else None
            res.append(
                DoorStatus(
                    cabinet_type="disshoegoods",
                    cabinet_key=cab_key,
                    cabinet_name=cab_name,
                    device_id=str(device_id),
                    address=int(address) if str(address).isdigit() else None,
                    door_no=box_no,
                    door_name=str(box_no),
                    user_id=uid,
                    user_name=uname,
                    lock_state=st,
                    lock_name=st_name,
                    size_name=size_name,
                    style_name=style_name,
                    device_name=None,
                )
            )
        return res

    def update_disshoe_user(self, device_id: str, address: int, box_no: int, user_id: Optional[str]):
        """Set DisShoeGoods.UserId for a single slot (None => cycle)."""
        sql = """
        UPDATE OperRoom.dbo.DisShoeGoods
        SET UserId = ?
        WHERE DeviceId = ? AND Address = ? AND BoxNo = ?
        """
        with self._conn() as conn:
            conn.cursor().execute(sql, user_id, device_id, address, box_no)
            conn.commit()
