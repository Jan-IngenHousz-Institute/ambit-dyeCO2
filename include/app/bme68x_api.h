#pragma once

extern bool bme_available;

bool initBME(void);
bool bme_read(void);
void cmd_bme_read();

