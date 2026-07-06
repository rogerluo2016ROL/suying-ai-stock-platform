package com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class IntentResult {
    private String intent;
    private double confidence;
    private String reason;
}
