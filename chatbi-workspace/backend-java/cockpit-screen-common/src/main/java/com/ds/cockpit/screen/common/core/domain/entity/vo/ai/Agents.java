package com.ds.cockpit.screen.common.core.domain.entity.vo.ai;

import com.alibaba.fastjson2.JSONObject;
import lombok.Data;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-12 上午 10:38
 */
@Data
public class Agents {

    Long update_time;
    Object canvas_type;
    Long create_time;
    String user_id;
    Object description;
    String permission;
    Object avatar;
    String id;
    String create_date;
    JSONObject dsl;
    String title;
    String update_date;

}
