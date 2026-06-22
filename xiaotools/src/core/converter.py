import pandas as pd
import re

class TiaToKingscadaConverter:
    def __init__(self, config):
        self.config = config
        # 新增：记录每个字节已使用的位（避免重复）
        self.current_byte_bits = {}  # 格式：{字节: [已使用的位列表]}
        
        # 数据类型映射 - 包含DInt类型
        self.data_type_map = {
            'Bool': {'tag_data_type': 'IODisc', 'item_data_type': 'BIT'},
            'Int': {'tag_data_type': 'IOShort', 'item_data_type': 'SHORT',
                   'max_raw': '32767', 'min_raw': '-32767',
                   'max_value': '32767', 'min_value': '-32767'},
            'UInt': {'tag_data_type': 'IOShort', 'item_data_type': 'SHORT',
                   'max_raw': '32767', 'min_raw': '-32767',
                   'max_value': '32767', 'min_value': '-32767'},
            'Real': {'tag_data_type': 'IOFloat', 'item_data_type': 'FLOAT',
                    'max_raw': '1000000000', 'min_raw': '-1000000000',
                    'max_value': '1000000000', 'min_value': '-1000000000'},
            'DInt': {'tag_data_type': 'IOLong', 'item_data_type': 'LONG',
                    'max_raw': '999999999', 'min_raw': '-999999999',
                    'max_value': '999999999', 'min_value': '-999999999'},
            'Word': {'tag_data_type': 'IOWord', 'item_data_type': 'SHORT',
                    'max_raw': '65535', 'min_raw': '0',
                    'max_value': '65535', 'min_value': '0'},
            'DWord': {'tag_data_type': 'IODWord', 'item_data_type': 'DWORD',
                     'max_raw': '4294967295', 'min_raw': '0',
                     'max_value': '4294967295', 'min_value': '0'}
        }
        
        # 字段定义 - 添加UANodePath列
        self.field_names = [
            'TagID', 'TagName', 'Description', 'TagType', 'TagDataType',
            'MaxRawValue', 'MinRawValue', 'MaxValue', 'MinValue',
            'NonLinearTableName', 'ConvertType', 'IsFilter', 'DeadBand',
            'Unit', 'ChannelName', 'DeviceName', 'ChannelDriver',
            'DeviceSeries', 'DeviceSeriesType', 'CollectControl',
            'CollectInterval', 'CollectOffset', 'TimeZoneBias',
            'TimeAdjustment', 'Enable', 'ForceWrite', 'ItemName',
            'RegName', 'RegType', 'ItemDataType', 'ItemAccessMode',
            'HisRecordMode', 'HisDeadBand', 'HisInterval', 'TagGroup',
            'NamespaceIndex', 'IdentifierType', 'Identifier', 'ValueRank',
            'QueueSize', 'DiscardOldest', 'MonitoringMode', 'TriggerMode',
            'DeadType', 'DeadValue', 'UANodePath'
        ]
        
        # 定义所有支持的数据类型
        self.support_types = {'Bool','Int','UInt','Real','DInt','Word','DWord','BOOL','INT','UINT','REAL','DINT','WORD','DWORD','dint','bool','int','uint','real','word','dword'}

    def reset_byte_bit_record(self):
        """重置字节位记录（每次转换新文件时调用）"""
        self.current_byte_bits = {}

    def convert(self, input_text):
        # 解析TIA文本
        parsed_data = self.parse_tia_text(input_text)
        
        # 转换为DataFrame
        df = self.create_dataframe(parsed_data)
        
        # 生成统计信息
        stats = self.generate_stats(df, parsed_data)
        
        return {
            'dataframe': df,
            'stats': stats,
            'parsed_data': parsed_data
        }
    
    def parse_tia_text(self, text):
        lines = text.strip().split('\n')
        parsed_data = []
        # ✅ 核心修改1：取消所有默认兜底值，初始化为空
        current_device = ""
        current_prefix_desc = ""

        # 数据类型映射（增强支持更多格式）
        data_type_aliases = {
            'DInt': 'DInt', 'DINT': 'DInt', 'dint': 'DInt', 'Dint': 'DInt', 'Long': 'DInt', 'LONG': 'DInt',
            'Bool': 'Bool', 'BOOL': 'Bool', 'bool': 'Bool', 'Bool': 'Bool',
            'Int': 'Int', 'INT': 'Int', 'int': 'Int', 'Int': 'Int', 'Short': 'Int', 'SHORT': 'Int',
            'UInt': 'UInt', 'UINT': 'UInt', 'uint': 'UInt', 'Uint': 'UInt',
            'Real': 'Real', 'REAL': 'Real', 'real': 'Real', 'Real': 'Real', 'Float': 'Real', 'FLOAT': 'Real',
            'Word': 'Word', 'WORD': 'Word', 'word': 'Word', 'Word': 'Word',
            'DWord': 'DWord', 'DWORD': 'DWord', 'dword': 'DWord', 'Dword': 'DWord',
            'String': 'String', 'STRING': 'String'
        }
        
        for line in lines:
            if not line.strip():
                continue
                
            # 兼容 TIA 导出的【制表符+\t】和【空格】混合分隔，彻底解析无残留
            parts = re.split(r'\t+|\s{2,}', line.strip())

            # ✅ 核心修改2：自动识别【设备行】- 无数据类型的行就是设备行
            if len(parts)>=2 and parts[1] not in self.support_types:
                current_device = parts[0].strip()      # 取第一列：DOS_FL_FIT0102
                current_prefix_desc = parts[-1].strip()# 取最后一列：磁混凝(东)_2#加药流量计
                continue
            
            # ✅ 核心修改3：只解析【变量行】- 有数据类型+有设备行前置，才解析
            if current_device and len(parts)>=4 and parts[1] in self.support_types:
                variable_name = parts[0].strip()
                original_data_type = parts[1].strip()
                data_type = data_type_aliases.get(original_data_type, original_data_type)
                
                # 数据类型兼容（增强处理逻辑）
                if data_type not in self.data_type_map:
                    if 'int' in data_type.lower() and 'd' in data_type.lower():
                        data_type = 'DInt'
                    elif 'uint' in data_type.lower():
                        data_type = 'UInt'
                    elif 'real' in data_type.lower() or 'float' in data_type.lower():
                        data_type = 'Real'
                    elif 'bool' in data_type.lower():
                        data_type = 'Bool'
                    elif 'word' in data_type.lower() and 'd' in data_type.lower():
                        data_type = 'DWord'
                    elif 'word' in data_type.lower():
                        data_type = 'Word'
                    else:
                        data_type = 'Int'

                offset_str = parts[2].strip()
                default_value = parts[3].strip() if len(parts) > 3 else ''
                variable_desc = parts[-1].strip() if len(parts)>=5 else variable_name
                
                # ✅ 终极需求：严格拼接，无任何多余值
                final_tag_name = f"{current_device}_{variable_name}"          # DOS_FL_FIT0102_W_DDZ
                final_description = f"{current_prefix_desc}_{variable_desc}" # 磁混凝(东)_2#加药流量计_复位死区设置

                # 提取单位（原有功能，不影响注释内容，保留）
                unit = ''
                if final_description:
                    unit_match = re.search(r'\(([^)]+)\)', final_description)
                    if unit_match:
                        unit = unit_match.group(1)

                parsed_data.append({
                    'device': current_device,
                    'variable': variable_name,
                    'original_data_type': original_data_type,
                    'data_type': data_type,
                    'offset': offset_str,
                    'default_value': default_value,
                    'description': final_description,
                    'unit': unit
                })
        
        return parsed_data

    def create_dataframe(self, parsed_data):
        rows = []
        tag_id = self.config['start_tag_id']
        
        for item in parsed_data:
            data_type_info = self.data_type_map.get(item['data_type'], self.data_type_map['Bool'])
            reg_name = self.generate_reg_address(item['offset'], item['data_type'])
            access_mode = self.get_access_mode(item['variable'])
            dead_value = self.process_default_value(item['default_value'], item['data_type'])
            
            row = {
                'TagID': tag_id,
                'TagName': item['device'] + "_" + item['variable'],  # 再次确认拼接规则
                'Description': item['description'],
                'TagType': '用户变量',
                'TagDataType': data_type_info['tag_data_type'],
                'MaxRawValue': data_type_info.get('max_raw', ''),
                'MinRawValue': data_type_info.get('min_raw', ''),
                'MaxValue': data_type_info.get('max_value', ''),
                'MinValue': data_type_info.get('min_value', ''),
                'NonLinearTableName': '',
                'ConvertType': '无',
                'IsFilter': '否',
                'DeadBand': '0',
                'Unit': '',
                'ChannelName': self.config['channel_name'],
                'DeviceName': self.config['device_name'],
                'ChannelDriver': self.config['driver'],
                'DeviceSeries': self.config['device_series'],
                'DeviceSeriesType': '0',
                'CollectControl': '否',
                'CollectInterval': str(self.config['collect_interval']),
                'CollectOffset': '0',
                'TimeZoneBias': '0',
                'TimeAdjustment': '0',
                'Enable': '是',
                'ForceWrite': '否',
                'ItemName': reg_name,
                'RegName': 'DB',
                'RegType': str(self.config['default_db_number']),
                'ItemDataType': data_type_info['item_data_type'],
                'ItemAccessMode': access_mode,
                'HisRecordMode': '不记录',
                'HisDeadBand': '0',
                'HisInterval': str(self.config['his_interval']),
                'TagGroup': self.config['tag_group'],
                'NamespaceIndex': '0',
                'IdentifierType': '0',
                'Identifier': '',
                'ValueRank': '-1',
                'QueueSize': '1',
                'DiscardOldest': '0',
                'MonitoringMode': '0',
                'TriggerMode': '0',
                'DeadType': '0',
                'DeadValue': '0',
                'UANodePath': ''
            }
            
            rows.append(row)
            tag_id += 1
        
        return pd.DataFrame(rows, columns=self.field_names)
    
    def process_default_value(self, default_value, data_type):
        """处理默认值，转换为合适的格式"""
        if not default_value:
            return ''
        default_value = str(default_value).strip()
        try:
            if data_type == 'Bool':
                if default_value.upper() in ['TRUE', '1', 'YES']:
                    return '1'
                elif default_value.upper() in ['FALSE', '0', 'NO']:
                    return '0'
                else:
                    return default_value
            elif data_type in ['Int', 'DInt']:
                return str(int(float(default_value)))
            elif data_type == 'Real':
                return str(float(default_value))
            else:
                return default_value
        except (ValueError, TypeError):
            return default_value
    
    def generate_reg_address(self, offset_str, data_type):
        db_number = self.config['default_db_number']
        try:
            offset = float(offset_str)
            byte_part = int(offset)

            if data_type == 'Bool':
                bit_part = int(round((offset - byte_part) * 10))
                return f"DB{db_number}.{byte_part}.{bit_part}"
            else:
                return f"DB{db_number}.{byte_part}"

        except Exception:
            return f"DB{db_number}.{offset_str}"

    
    def get_access_mode(self, variable_name):
        # 读写权限规则保留，不影响变量名/描述
        if variable_name.startswith(('C_', 'W_')):
            return '读写'
        else:
            return '只读'

    def convert_tag_list(self, tag_data_list):
        """转换Tag列表（入口方法）"""
        self.reset_byte_bit_record()  # 转换前重置位记录
        converted_tags = []
        for tag_data in tag_data_list:
            tag_id = tag_data['TagID']
            tag_name = tag_data['TagName']
            description = tag_data['Description']
            data_type = tag_data['DataType']
            offset_str = tag_data['IODisc']  # 假设IODisc对应偏移量字段

            # 生成地址
            address = self.generate_reg_address(offset_str, data_type)
            
            converted_tags.append({
                'TagID': tag_id,
                'TagName': tag_name,
                'Description': description,
                'DataType': data_type,
                'Address': address
            })
        return converted_tags

    def generate_stats(self, df, parsed_data):
        """生成统计信息"""
        devices = set(item['device'] for item in parsed_data)
        bool_count = len(df[df['TagDataType'] == 'IODisc'])
        int_count = len(df[df['TagDataType'] == 'IOShort'])
        real_count = len(df[df['TagDataType'] == 'IOFloat'])
        dint_count = len(df[df['TagDataType'] == 'IOLong'])
        word_count = len(df[df['TagDataType'] == 'IOWord'])
        dword_count = len(df[df['TagDataType'] == 'IODWord'])
        rw_count = len(df[df['ItemAccessMode'] == '读写'])
        ro_count = len(df[df['ItemAccessMode'] == '只读'])
        device_count = len(devices)
        total_points = len(df)

        # 打印统计信息，用于调试
        print(f"generate_stats - total_points: {total_points}")
        print(f"generate_stats - bool_count: {bool_count}")
        print(f"generate_stats - real_count: {real_count}")
        print(f"generate_stats - int_count: {int_count}")
        print(f"generate_stats - dint_count: {dint_count}")
        print(f"generate_stats - dword_count: {dword_count}")

        stats = {
            'total_points': total_points,
            'bool_count': bool_count,
            'int_count': int_count,
            'real_count': real_count,
            'dint_count': dint_count,
            'word_count': word_count,
            'dword_count': dword_count,
            'rw_count': rw_count,
            'ro_count': ro_count,
            'device_count': device_count
        }
        return stats

    def create_multi_sheet_dataframes(self, df):
        """按TagDataType将数据拆分为多个DataFrame（多sheet）"""
        # IO类型到sheet名称的映射
        sheet_mapping = {
            'IODisc': 'IO_DISC',
            'IOChar': 'IO_CHAR',
            'IOByte': 'IO_BYTE',
            'IOShort': 'IO_SHORT',
            'IOWord': 'IO_WORD',
            'IOLong': 'IO_LONG',
            'IODWord': 'IO_DWORD',
            'IOInt64': 'IO_INT64',
            'IOFloat': 'IO_FLOAT',
            'IODouble': 'IO_DOUBLE',
            'IOString': 'IO_STRING',
            'IOBlob': 'IO_BLOB'
        }

        # 需要保留的字段（按用户要求）
        output_fields = [
            'TagID', 'TagName', 'Description', 'TagType', 'TagDataType',
            'ChannelName', 'DeviceName', 'ChannelDriver', 'DeviceSeries', 
            'DeviceSeriesType', 'CollectControl', 'CollectInterval', 
            'CollectOffset', 'TimeZoneBias', 'TimeAdjustment', 'Enable', 
            'ForceWrite', 'ItemName', 'RegName', 'RegType', 'ItemDataType', 
            'ItemAccessMode', 'HisRecordMode', 'HisDeadBand', 'HisInterval', 'TagGroup'
        ]

        # 初始化所有sheet的空DataFrame
        sheets = {}
        for sheet_name in sheet_mapping.values():
            sheets[sheet_name] = pd.DataFrame(columns=output_fields)

        # 按TagDataType分组并填充到对应的sheet
        for tag_type, group in df.groupby('TagDataType'):
            sheet_name = sheet_mapping.get(tag_type)
            if sheet_name:
                sheets[sheet_name] = group[output_fields].reset_index(drop=True)

        return sheets
