package com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ChatBIAgentVO {
    private String id;
    private String code;
    private String name;
    private String description;
}
